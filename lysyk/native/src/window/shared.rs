#[cfg(not(target_os = "android"))]
use std::cell::RefCell;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use numpy::{PyArray1, PyArray3, PyArrayMethods};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use winit::application::ApplicationHandler;
use winit::dpi::{LogicalSize, PhysicalPosition};
use winit::event::{ElementState, MouseButton, MouseScrollDelta, TouchPhase, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::keyboard::{KeyCode, PhysicalKey};
use winit::window::{Fullscreen, Window, WindowAttributes, WindowId};

use crate::canvas::Canvas;
use crate::devtools::{copy_to_buffer, draw_overlay, finish_readback, write_png};
use crate::gpu::{open, Api, Gpu, Timer};
use crate::keys::glfw_code;

#[pyclass(module = "lysyk.engine._native")]
pub struct GpuHandle {
    pub gpu: Arc<Gpu>,
}

#[pymethods]
impl GpuHandle {
    #[getter]
    fn api(&self) -> &'static str {
        self.gpu.api_name
    }

    fn info<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        adapter_info_dict(py, &self.gpu.info, self.gpu.api_name)
    }

    fn profile<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let hist = self.gpu.profiler.history();
        let d = PyDict::new(py);
        let n = hist.len().max(1) as f32;
        d.set_item("frames", self.gpu.profiler.inner.lock().unwrap().frames)?;
        d.set_item("avg_ms", hist.iter().map(|r| r.total).sum::<f32>() / n)?;
        let mut t: Vec<f32> = hist.iter().map(|r| r.total).collect();
        t.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let q = |p: f32| {
            if t.is_empty() {
                0.0
            } else {
                t[((t.len() as f32 * p) as usize).min(t.len() - 1)]
            }
        };
        d.set_item("p50_ms", q(0.5))?;
        d.set_item("p99_ms", q(0.99))?;
        d.set_item("max_ms", t.last().copied().unwrap_or(0.0))?;
        let stages = PyDict::new(py);
        for (k, name) in crate::gpu::STAGES.iter().enumerate() {
            stages.set_item(*name, hist.iter().map(|r| r.stages[k]).sum::<f32>() / n)?;
        }
        d.set_item("stages_ms", stages)?;
        d.set_item(
            "history_ms",
            hist.iter().map(|r| r.total).collect::<Vec<f32>>(),
        )?;
        Ok(d)
    }
}

pub fn adapter_info_dict<'py>(
    py: Python<'py>,
    i: &wgpu::AdapterInfo,
    api: &str,
) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("name", &i.name)?;
    d.set_item("device", &i.name)?;
    d.set_item("api", api)?;
    d.set_item("backend_type", crate::gpu::backend_label(i.backend))?;
    d.set_item("adapter_type", format!("{:?}", i.device_type))?;
    d.set_item("driver", &i.driver)?;
    d.set_item("driver_info", &i.driver_info)?;
    d.set_item("vendor_id", i.vendor)?;
    d.set_item("device_id", i.device)?;
    Ok(d)
}

struct Inner {
    surface: Option<wgpu::Surface<'static>>,
    vsync: bool,
    frame_interval: f64,
    fullscreen: bool,
    windowed_rect: Option<(i32, i32, u32, u32)>,
    width: u32,
    height: u32,
    pixel_ratio: f64,
    mouse: (f64, f64),
    title: String,
    fps: f64,
    frame_ms: f64,
    overlay: bool,
    mods: u32,
    touch: Option<u64>,
    emulate_touch: bool,
    touch_seen: bool,
}

pub struct Shared {
    gpu: Arc<Gpu>,
    window: Mutex<Option<Arc<Window>>>,
    inner: Mutex<Inner>,
    canvas: Py<Canvas>,
}

#[cfg(not(target_os = "android"))]
thread_local! {
    static CLIP: RefCell<Option<arboard::Clipboard>> = const { RefCell::new(None) };
}

fn begin_frame(py: Python<'_>, gpu: &Gpu, canvas: &Py<Canvas>, view: wgpu::TextureView) {
    {
        let mut st = gpu.state.lock().unwrap();
        st.frame_view = Some(view);
        st.encoder = Some(
            gpu.device
                .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                    label: Some("frame"),
                }),
        );
        st.pass_recorded = false;
    }
    canvas.bind(py).borrow_mut().begin_frame();
}

struct Finished {
    readback: Option<(wgpu::Buffer, u32)>,
}

fn end_frame(
    py: Python<'_>,
    gpu: &Gpu,
    canvas: &Py<Canvas>,
    w: u32,
    h: u32,
    overlay: Option<f64>,
    copy_from: Option<&wgpu::Texture>,
) -> Finished {
    let (mut enc, view, format, clear, recorded) = {
        let mut st = gpu.state.lock().unwrap();
        let Some(enc) = st.encoder.take() else {
            return Finished { readback: None };
        };
        (
            enc,
            st.frame_view.take().unwrap(),
            st.format,
            st.clear,
            st.pass_recorded,
        )
    };
    if !recorded {
        let _ = enc.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("clear"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view: &view,
                depth_slice: None,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Clear(wgpu::Color {
                        r: clear[0] as f64,
                        g: clear[1] as f64,
                        b: clear[2] as f64,
                        a: 1.0,
                    }),
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
            multiview_mask: None,
        });
    }
    let mut timer = Timer::start();
    {
        let mut cv = canvas.bind(py).borrow_mut();
        if let Some(fps) = overlay {
            draw_overlay(&mut cv, gpu, w as f32, h as f32, fps);
        }
        cv.flush(&mut enc, &view, w, h, format);
    }
    gpu.profiler.add(6, timer.lap());
    let readback = copy_from.map(|t| copy_to_buffer(gpu, &mut enc, t, w, h));
    gpu.queue.submit([enc.finish()]);
    gpu.profiler.add(7, timer.lap());
    Finished { readback }
}

fn is_bgra(f: wgpu::TextureFormat) -> bool {
    matches!(
        f,
        wgpu::TextureFormat::Bgra8Unorm | wgpu::TextureFormat::Bgra8UnormSrgb
    )
}

