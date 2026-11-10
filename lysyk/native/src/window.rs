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

#[pyclass(unsendable, module = "lysyk.engine._native")]
pub struct WindowCore {
    shared: Arc<Shared>,
    event_loop: Option<EventLoop<()>>,
    handle: Py<GpuHandle>,
}

#[cfg(all(target_os = "android", feature = "android-host"))]
fn make_event_loop() -> Result<EventLoop<()>, String> {
    use winit::platform::android::EventLoopBuilderExtAndroid;
    let app =
        crate::android::app().ok_or_else(|| "the Android app handle is not set".to_string())?;
    EventLoop::builder()
        .with_android_app(app)
        .build()
        .map_err(|e| e.to_string())
}

#[cfg(not(all(target_os = "android", feature = "android-host")))]
fn make_event_loop() -> Result<EventLoop<()>, String> {
    EventLoop::new().map_err(|e| e.to_string())
}

struct SendBox<T>(T);
unsafe impl<T> Send for SendBox<T> {}

#[pymethods]
impl WindowCore {
    #[new]
    #[pyo3(signature = (width, height, title, resizable=true, vsync=true, msaa=true, api="auto", fonts_dir=""))]
    #[allow(deprecated)]
    fn new(
        py: Python<'_>,
        width: u32,
        height: u32,
        title: &str,
        resizable: bool,
        vsync: bool,
        msaa: bool,
        api: &str,
        fonts_dir: &str,
    ) -> PyResult<Self> {
        let api = Api::parse(&std::env::var("LYSYK_BACKEND").unwrap_or_else(|_| api.to_string()))?;
        let event_loop = make_event_loop().map_err(|e| {
            PyRuntimeError::new_err(format!("cannot create the event loop (no display?): {e}"))
        })?;
        let attrs = WindowAttributes::default()
            .with_title(title)
            .with_resizable(resizable)
            .with_inner_size(LogicalSize::new(width as f64, height as f64));
        let window: Option<Arc<Window>> = if cfg!(target_os = "android") {
            None
        } else {
            Some(Arc::new(
                event_loop
                    .create_window(attrs)
                    .map_err(|e| PyRuntimeError::new_err(e.to_string()))?,
            ))
        };
        let display_handle = event_loop.owned_display_handle();
        let display = move || {
            Some(Box::new(display_handle.clone()) as Box<dyn wgpu::wgt::WgpuHasDisplayHandle>)
        };
        let (pw, ph, ratio) = match &window {
            Some(w) => {
                let s = w.inner_size();
                (s.width.max(1), s.height.max(1), w.scale_factor())
            }
            None => (width, height, 1.0),
        };
        let wclone = window.clone();
        let make_surface = move |inst: &wgpu::Instance| -> Option<wgpu::Surface<'static>> {
            wclone
                .as_ref()
                .and_then(|w| inst.create_surface(w.clone()).ok())
        };
        let opened = py.detach(|| open(api, msaa, pw, ph, &display, Some(&make_surface)))?;
        let gpu = opened.gpu;
        if let Some(s) = &opened.surface {
            gpu.configure_surface(s, pw, ph, vsync);
        }
        let fonts = PathBuf::from(fonts_dir);
        let canvas = Py::new(py, Canvas::new_inner(gpu.clone(), &fonts))?;
        let shared = Arc::new(Shared {
            gpu: gpu.clone(),
            window: Mutex::new(window),
            inner: Mutex::new(Inner {
                surface: opened.surface,
                vsync,
                frame_interval: 0.0,
                fullscreen: false,
                windowed_rect: None,
                width: pw,
                height: ph,
                pixel_ratio: ratio,
                mouse: (0.0, 0.0),
                title: title.to_string(),
                fps: 0.0,
                frame_ms: 0.0,
                overlay: std::env::var("LYSYK_OVERLAY").map_or(false, |v| v == "1"),
                mods: 0,
                touch: None,
                emulate_touch: true,
                touch_seen: false,
            }),
            canvas,
        });
        let handle = Py::new(py, GpuHandle { gpu })?;
        Ok(WindowCore {
            shared,
            event_loop: Some(event_loop),
            handle,
        })
    }

    #[getter]
    fn gpu(&self, py: Python<'_>) -> Py<GpuHandle> {
        self.handle.clone_ref(py)
    }

    #[getter]
    fn canvas(&self, py: Python<'_>) -> Py<Canvas> {
        self.shared.canvas.clone_ref(py)
    }

    #[getter]
    fn width(&self) -> u32 {
        self.shared.inner.lock().unwrap().width
    }

    #[getter]
    fn height(&self) -> u32 {
        self.shared.inner.lock().unwrap().height
    }

    #[getter]
    fn pixel_ratio(&self) -> f64 {
        self.shared.inner.lock().unwrap().pixel_ratio
    }

    #[getter]
    fn mouse_x(&self) -> f64 {
        self.shared.inner.lock().unwrap().mouse.0
    }

    #[getter]
    fn mouse_y(&self) -> f64 {
        self.shared.inner.lock().unwrap().mouse.1
    }

    #[getter]
    fn fps(&self) -> f64 {
        self.shared.inner.lock().unwrap().fps
    }

    #[getter]
    fn frame_time_ms(&self) -> f64 {
        self.shared.inner.lock().unwrap().frame_ms
    }

    #[getter]
    fn fullscreen(&self) -> bool {
        self.shared.inner.lock().unwrap().fullscreen
    }

    #[getter]
    fn title(&self) -> String {
        self.shared.inner.lock().unwrap().title.clone()
    }

    #[getter]
    fn overlay(&self) -> bool {
        self.shared.inner.lock().unwrap().overlay
    }

    #[setter]
    fn set_overlay(&self, v: bool) {
        self.shared.inner.lock().unwrap().overlay = v;
    }

    fn set_title(&self, title: &str) {
        self.shared.inner.lock().unwrap().title = title.to_string();
        if let Some(w) = self.shared.window.lock().unwrap().as_ref() {
            w.set_title(title);
        }
    }

    fn set_vsync(&self, enabled: bool) {
        let mut i = self.shared.inner.lock().unwrap();
        if i.vsync == enabled {
            return;
        }
        i.vsync = enabled;
        if let Some(s) = &i.surface {
            self.shared
                .gpu
                .configure_surface(s, i.width, i.height, enabled);
        }
    }

    fn set_fps_limit(&self, fps: f64) {
        self.shared.inner.lock().unwrap().frame_interval = if fps > 0.0 { 1.0 / fps } else { 0.0 };
    }

    fn set_msaa(&self, enabled: bool) {
        self.shared.gpu.set_msaa(enabled);
    }

    fn msaa_samples(&self) -> u32 {
        self.shared.gpu.state.lock().unwrap().sample_count
    }

    fn clear(&self, color: (f64, f64, f64)) {
        self.shared.gpu.state.lock().unwrap().clear = [
            (color.0 / 255.0) as f32,
            (color.1 / 255.0) as f32,
            (color.2 / 255.0) as f32,
        ];
    }

    fn set_fullscreen(&self, enabled: bool) {
        let mut i = self.shared.inner.lock().unwrap();
        if i.fullscreen == enabled {
            return;
        }
        let guard = self.shared.window.lock().unwrap();
        let Some(w) = guard.as_ref() else { return };
        if enabled {
            let pos = w
                .outer_position()
                .unwrap_or(PhysicalPosition::new(100, 100));
            let size = w.inner_size();
            i.windowed_rect = Some((pos.x, pos.y, size.width, size.height));
            w.set_fullscreen(Some(Fullscreen::Borderless(None)));
        } else {
            w.set_fullscreen(None);
        }
        i.fullscreen = enabled;
    }

    fn monitor_info<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyDict>>> {
        let guard = self.shared.window.lock().unwrap();
        let Some(m) = guard
            .as_ref()
            .and_then(|w| w.current_monitor().or_else(|| w.primary_monitor()))
        else {
            return Ok(None);
        };
        let d = PyDict::new(py);
        d.set_item("name", m.name().unwrap_or_default())?;
        d.set_item("width", m.size().width)?;
        d.set_item("height", m.size().height)?;
        d.set_item(
            "refresh",
            m.refresh_rate_millihertz()
                .map_or(0, |r| (r as f64 / 1000.0).round() as u32),
        )?;
        Ok(Some(d))
    }

    fn set_cursor_visible(&self, visible: bool) {
        let guard = self.shared.window.lock().unwrap();
        if let Some(w) = guard.as_ref() {
            w.set_cursor_visible(visible);
        }
    }

    fn set_cursor_grab(&self, mode: &str) -> bool {
        use winit::window::CursorGrabMode;
        let guard = self.shared.window.lock().unwrap();
        let Some(w) = guard.as_ref() else {
            return false;
        };
        match mode {
            "confined" => w.set_cursor_grab(CursorGrabMode::Confined).is_ok(),
            "locked" => {
                w.set_cursor_grab(CursorGrabMode::Locked).is_ok()
                    || w.set_cursor_grab(CursorGrabMode::Confined).is_ok()
            }
            _ => w.set_cursor_grab(CursorGrabMode::None).is_ok(),
        }
    }

    #[getter]
    fn is_mobile(&self) -> bool {
        cfg!(target_os = "android") || self.shared.inner.lock().unwrap().touch_seen
    }

    #[getter]
    fn touch_emulates_mouse(&self) -> bool {
        self.shared.inner.lock().unwrap().emulate_touch
    }

    #[setter]
    fn set_touch_emulates_mouse(&self, v: bool) {
        self.shared.inner.lock().unwrap().emulate_touch = v;
    }

    fn center_window(&self) {
        let guard = self.shared.window.lock().unwrap();
        let Some(w) = guard.as_ref() else { return };
        if let Some(m) = w.current_monitor().or_else(|| w.primary_monitor()) {
            let (ms, mp, ws) = (m.size(), m.position(), w.outer_size());
            w.set_outer_position(PhysicalPosition::new(
                mp.x + (ms.width as i32 - ws.width as i32) / 2,
                mp.y + (ms.height as i32 - ws.height as i32) / 2,
            ));
        }
    }

    fn close(&self) {
        CLOSE.with(|c| c.set(true));
    }

    fn set_clipboard(&self, text: &str) {
        #[cfg(not(target_os = "android"))]
        CLIP.with(|c| {
            let mut c = c.borrow_mut();
            if c.is_none() {
                *c = arboard::Clipboard::new().ok();
            }
            if let Some(cb) = c.as_mut() {
                let _ = cb.set_text(text.to_string());
            }
        });
        let _ = text;
    }

    fn screenshot(&self, path: &str) {
        *self.shared.gpu.screenshot.lock().unwrap() = Some(path.to_string());
    }

    fn run(slf: &Bound<'_, Self>, py: Python<'_>, handler: Py<PyAny>) -> PyResult<()> {
        let (shared, event_loop) = {
            let mut me = slf.borrow_mut();
            let el = me
                .event_loop
                .take()
                .ok_or_else(|| PyRuntimeError::new_err("run() was already called"))?;
            (me.shared.clone(), el)
        };
        CLOSE.with(|c| c.set(false));
        let mut app = App {
            shared: shared.clone(),
            handler: handler.clone_ref(py),
            error: None,
            last: Instant::now(),
            fps_t: Instant::now(),
            fps_n: 0,
            started: false,
        };
        let pack = SendBox((event_loop, &mut app));
        let result = py.detach(move || {
            let pack = pack;
            let (el, app) = pack.0;
            el.run_app(app)
        });
        if let Some(e) = app.error.take() {
            return Err(e);
        }
        result.map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        handler.bind(py).call_method0("on_close")?;
        Ok(())
    }
}

thread_local! {
    static CLOSE: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

struct App {
    shared: Arc<Shared>,
    handler: Py<PyAny>,
    error: Option<PyErr>,
    last: Instant,
    fps_t: Instant,
    fps_n: u32,
    started: bool,
}

impl App {
    fn call(
        &mut self,
        el: &ActiveEventLoop,
        py: Python<'_>,
        name: &str,
        args: impl for<'a> pyo3::call::PyCallArgs<'a>,
    ) {
        if self.error.is_some() {
            return;
        }
        if let Err(e) = self.handler.bind(py).call_method1(name, args) {
            self.error = Some(e);
            el.exit();
        }
    }

    fn ensure_surface(&mut self) {
        let window = self.shared.window.lock().unwrap().clone();
        let Some(w) = window else { return };
        let mut i = self.shared.inner.lock().unwrap();
        if i.surface.is_none() {
            if let Ok(s) = self.shared.gpu.instance.create_surface(w.clone()) {
                let size = w.inner_size();
                i.width = size.width.max(1);
                i.height = size.height.max(1);
                self.shared
                    .gpu
                    .configure_surface(&s, i.width, i.height, i.vsync);
                i.surface = Some(s);
            }
        }
    }

    fn frame(&mut self, el: &ActiveEventLoop) {
        let shared = self.shared.clone();
        let gpu = shared.gpu.clone();
        let (w, h) = {
            let i = shared.inner.lock().unwrap();
            (i.width, i.height)
        };
        if w == 0 || h == 0 {
            return;
        }
        let tex = {
            let i = shared.inner.lock().unwrap();
            let Some(s) = i.surface.as_ref() else { return };
            let mut tm = Timer::start();
            let r = s.get_current_texture();
            let waited = tm.lap();
            drop(i);
            match r {
                wgpu::CurrentSurfaceTexture::Success(t)
                | wgpu::CurrentSurfaceTexture::Suboptimal(t) => Some((t, waited)),
                wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                    let i = shared.inner.lock().unwrap();
                    let (iw, ih, v) = (i.width, i.height, i.vsync);
                    if let Some(s) = i.surface.as_ref() {
                        gpu.configure_surface(s, iw, ih, v);
                    }
                    None
                }
                _ => None,
            }
        };
        let Some((frame, waited)) = tex else { return };
        let started = Instant::now();
        let present_wait = std::cell::Cell::new(waited);
        let shot;
        let readback;
        let mut offscreen: Option<wgpu::Texture> = None;
        {
            let out = Python::attach(|py| {
                gpu.profiler.begin();
                let now = Instant::now();
                let dt = (now - self.last).as_secs_f64().min(0.1);
                self.last = now;
                shared.canvas.bind(py).borrow_mut().dt = dt;
                let mut timer = Timer::start();
                self.call(el, py, "on_update", (dt,));
                gpu.profiler.add(0, timer.lap());
                let pending = gpu.screenshot.lock().unwrap().take();
                let can_copy = frame
                    .texture
                    .usage()
                    .contains(wgpu::TextureUsages::COPY_SRC);
                let fmt = gpu.state.lock().unwrap().format;
                if pending.is_some() && !can_copy {
                    offscreen = Some(gpu.device.create_texture(&wgpu::TextureDescriptor {
                        label: Some("screenshot target"),
                        size: wgpu::Extent3d {
                            width: w,
                            height: h,
                            depth_or_array_layers: 1,
                        },
                        mip_level_count: 1,
                        sample_count: 1,
                        dimension: wgpu::TextureDimension::D2,
                        format: fmt,
                        usage: wgpu::TextureUsages::RENDER_ATTACHMENT
                            | wgpu::TextureUsages::COPY_SRC,
                        view_formats: &[],
                    }));
                }
                let target_tex = offscreen.as_ref().unwrap_or(&frame.texture);
                let view = target_tex.create_view(&wgpu::TextureViewDescriptor::default());
                begin_frame(py, &gpu, &shared.canvas, view);
                let mut t2 = Timer::start();
                self.call(el, py, "on_draw", ());
                gpu.profiler.add(1, t2.lap());
                let (overlay, fps) = {
                    let i = shared.inner.lock().unwrap();
                    (i.overlay, i.fps)
                };
                let fin = end_frame(
                    py,
                    &gpu,
                    &shared.canvas,
                    w,
                    h,
                    if overlay { Some(fps) } else { None },
                    if pending.is_some() {
                        Some(target_tex)
                    } else {
                        None
                    },
                );
                (pending, fin)
            });
            shot = out.0;
            readback = out.1.readback;
        }
        let mut tp = Timer::start();
        if offscreen.is_some() {
            drop(frame);
        } else {
            gpu.queue.present(frame);
        }
        present_wait.set(present_wait.get() + tp.lap());
        gpu.profiler.add(8, present_wait.get());
        gpu.profiler.end();
        if let (Some(path), Some((buf, bpr))) = (shot, readback) {
            let fmt = gpu.state.lock().unwrap().format;
            match finish_readback(&gpu, &buf, bpr, w, h, is_bgra(fmt))
                .and_then(|rb| write_png(&path, rb.width, rb.height, &rb.rgba))
            {
                Ok(()) => {
                    log::info!("screenshot saved to {path}");
                    *gpu.dev_message.lock().unwrap() = None;
                }
                Err(e) => log::error!("screenshot failed: {e}"),
            }
        }
        self.fps_n += 1;
        let el_t = self.fps_t.elapsed().as_secs_f64();
        let frame_ms = started.elapsed().as_secs_f64() * 1000.0;
        let interval = {
            let mut i = shared.inner.lock().unwrap();
            i.frame_ms = frame_ms;
            if el_t >= 0.5 {
                i.fps = self.fps_n as f64 / el_t;
                self.fps_n = 0;
                self.fps_t = Instant::now();
            }
            if i.vsync {
                0.0
            } else {
                i.frame_interval
            }
        };
        if interval > 0.0 {
            let target = started + Duration::from_secs_f64(interval);
            let now = Instant::now();
            if target > now + Duration::from_micros(1500) {
                std::thread::sleep(target - now - Duration::from_micros(1000));
            }
            while Instant::now() < target {
                std::thread::yield_now();
            }
        }
    }
}

impl ApplicationHandler for App {
    fn resumed(&mut self, el: &ActiveEventLoop) {
        #[allow(deprecated)]
        {
            let mut guard = self.shared.window.lock().unwrap();
            if guard.is_none() {
                let attrs = WindowAttributes::default()
                    .with_title(self.shared.inner.lock().unwrap().title.clone());
                match el.create_window(attrs) {
                    Ok(w) => *guard = Some(Arc::new(w)),
                    Err(e) => log::error!("cannot create window: {e}"),
                }
            }
        }
        self.ensure_surface();
        if let Some(w) = self.shared.window.lock().unwrap().as_ref() {
            w.request_redraw();
        }
        let (w, h) = {
            let i = self.shared.inner.lock().unwrap();
            (i.width, i.height)
        };
        if !self.started {
            self.started = true;
            self.last = Instant::now();
        } else {
            self.last = Instant::now();
            Python::attach(|py| {
                self.call(el, py, "on_resize", (w, h));
                self.call(el, py, "on_resume", ());
            });
        }
    }

    fn suspended(&mut self, el: &ActiveEventLoop) {
        #[cfg(target_os = "android")]
        {
            self.shared.inner.lock().unwrap().surface = None;
            *self.shared.window.lock().unwrap() = None;
        }
        Python::attach(|py| self.call(el, py, "on_suspend", ()));
    }

    fn window_event(&mut self, el: &ActiveEventLoop, _id: WindowId, event: WindowEvent) {
        if CLOSE.with(|c| c.get()) {
            el.exit();
            return;
        }
        match event {
            WindowEvent::CloseRequested => el.exit(),
            WindowEvent::Resized(size) => {
                let (w, h) = (size.width, size.height);
                {
                    let mut i = self.shared.inner.lock().unwrap();
                    i.width = w;
                    i.height = h;
                    if w > 0 && h > 0 {
                        if let Some(s) = i.surface.as_ref() {
                            self.shared.gpu.configure_surface(s, w, h, i.vsync);
                        }
                    }
                }
                if w > 0 && h > 0 {
                    Python::attach(|py| self.call(el, py, "on_resize", (w, h)));
                }
            }
            WindowEvent::ScaleFactorChanged { scale_factor, .. } => {
                self.shared.inner.lock().unwrap().pixel_ratio = scale_factor;
            }
            WindowEvent::ModifiersChanged(m) => {
                let s = m.state();
                let mut v = 0;
                if s.shift_key() {
                    v |= 1;
                }
                if s.control_key() {
                    v |= 2;
                }
                if s.alt_key() {
                    v |= 4;
                }
                if s.super_key() {
                    v |= 8;
                }
                self.shared.inner.lock().unwrap().mods = v;
            }
            WindowEvent::KeyboardInput { event, .. } => {
                let PhysicalKey::Code(code) = event.physical_key else {
                    return;
                };
                let Some(key) = glfw_code(code) else { return };
                let mods = self.shared.inner.lock().unwrap().mods;
                if event.state == ElementState::Pressed {
                    if !event.repeat {
                        if code == KeyCode::F3 {
                            let mut i = self.shared.inner.lock().unwrap();
                            i.overlay = !i.overlay;
                            return;
                        }
                        if code == KeyCode::F12 {
                            let stamp = std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .map_or(0, |d| d.as_secs());
                            *self.shared.gpu.screenshot.lock().unwrap() =
                                Some(format!("lysyk_{stamp}.png"));
                            return;
                        }
                    }
                    let repeatable = matches!(
                        code,
                        KeyCode::ArrowUp
                            | KeyCode::ArrowDown
                            | KeyCode::ArrowLeft
                            | KeyCode::ArrowRight
                    );
                    if !event.repeat || repeatable {
                        Python::attach(|py| self.call(el, py, "on_key_press", (key, mods)));
                    }
                } else {
                    Python::attach(|py| self.call(el, py, "on_key_release", (key, mods)));
                }
            }
            WindowEvent::CursorMoved { position, .. } => {
                self.shared.inner.lock().unwrap().mouse = (position.x, position.y);
                Python::attach(|py| self.call(el, py, "on_mouse_motion", (position.x, position.y)));
            }
            WindowEvent::MouseInput { state, button, .. } => {
                let b = match button {
                    MouseButton::Left => 0,
                    MouseButton::Right => 1,
                    MouseButton::Middle => 2,
                    _ => return,
                };
                let (x, y) = self.shared.inner.lock().unwrap().mouse;
                let name = if state == ElementState::Pressed {
                    "on_mouse_press"
                } else {
                    "on_mouse_release"
                };
                Python::attach(|py| self.call(el, py, name, (x, y, b)));
            }
            WindowEvent::MouseWheel { delta, .. } => {
                let (dx, dy) = match delta {
                    MouseScrollDelta::LineDelta(x, y) => (x as f64, y as f64),
                    MouseScrollDelta::PixelDelta(p) => (p.x / 40.0, p.y / 40.0),
                };
                Python::attach(|py| self.call(el, py, "on_scroll", (dx, dy)));
            }
            WindowEvent::Touch(t) => {
                let (x, y) = (t.location.x, t.location.y);
                let phase = match t.phase {
                    TouchPhase::Started => "down",
                    TouchPhase::Moved => "move",
                    TouchPhase::Ended => "up",
                    TouchPhase::Cancelled => "cancel",
                };
                let emulate = {
                    let mut i = self.shared.inner.lock().unwrap();
                    i.touch_seen = true;
                    i.emulate_touch
                };
                Python::attach(|py| self.call(el, py, "on_touch", (t.id, phase, x, y)));
                if !emulate {
                    return;
                }
                let mut i = self.shared.inner.lock().unwrap();
                match t.phase {
                    TouchPhase::Started if i.touch.is_none() => {
                        i.touch = Some(t.id);
                        i.mouse = (x, y);
                        drop(i);
                        Python::attach(|py| {
                            self.call(el, py, "on_mouse_motion", (x, y));
                            self.call(el, py, "on_mouse_press", (x, y, 0));
                        });
                    }
                    TouchPhase::Moved if i.touch == Some(t.id) => {
                        i.mouse = (x, y);
                        drop(i);
                        Python::attach(|py| self.call(el, py, "on_mouse_motion", (x, y)));
                    }
                    TouchPhase::Ended | TouchPhase::Cancelled if i.touch == Some(t.id) => {
                        i.touch = None;
                        i.mouse = (x, y);
                        drop(i);
                        Python::attach(|py| self.call(el, py, "on_mouse_release", (x, y, 0)));
                    }
                    _ => {}
                }
            }
            WindowEvent::RedrawRequested => {
                self.frame(el);
                if let Some(w) = self.shared.window.lock().unwrap().as_ref() {
                    w.request_redraw();
                }
            }
            _ => {}
        }
    }

    fn about_to_wait(&mut self, el: &ActiveEventLoop) {
        if self.error.is_some() || CLOSE.with(|c| c.get()) {
            el.exit();
            return;
        }
        if cfg!(target_os = "android") && self.shared.inner.lock().unwrap().surface.is_none() {
            return;
        }
        if let Some(w) = self.shared.window.lock().unwrap().as_ref() {
            w.request_redraw();
        }
    }
}

#[pyclass(module = "lysyk.engine._native")]
pub struct OffscreenCore {
    gpu: Arc<Gpu>,
    canvas: Py<Canvas>,
    handle: Py<GpuHandle>,
    texture: wgpu::Texture,
    width: u32,
    height: u32,
}

#[pymethods]
impl OffscreenCore {
    #[new]
    #[pyo3(signature = (width=1280, height=720, msaa=true, api="auto", fonts_dir=""))]
    fn new(
        py: Python<'_>,
        width: u32,
        height: u32,
        msaa: bool,
        api: &str,
        fonts_dir: &str,
    ) -> PyResult<Self> {
        let api = Api::parse(&std::env::var("LYSYK_BACKEND").unwrap_or_else(|_| api.to_string()))?;
        let opened = py.detach(|| open(api, msaa, width, height, &|| None, None))?;
        let gpu = opened.gpu;
        {
            let mut st = gpu.state.lock().unwrap();
            st.format = wgpu::TextureFormat::Rgba8Unorm;
        }
        let texture = gpu.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("offscreen"),
            size: wgpu::Extent3d {
                width,
                height,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
            view_formats: &[],
        });
        let canvas = Py::new(
            py,
            Canvas::new_inner(gpu.clone(), &PathBuf::from(fonts_dir)),
        )?;
        let handle = Py::new(py, GpuHandle { gpu: gpu.clone() })?;
        Ok(OffscreenCore {
            gpu,
            canvas,
            handle,
            texture,
            width,
            height,
        })
    }

    #[getter]
    fn gpu(&self, py: Python<'_>) -> Py<GpuHandle> {
        self.handle.clone_ref(py)
    }

    #[getter]
    fn canvas(&self, py: Python<'_>) -> Py<Canvas> {
        self.canvas.clone_ref(py)
    }

    #[getter]
    fn width(&self) -> u32 {
        self.width
    }

    #[getter]
    fn height(&self) -> u32 {
        self.height
    }

    fn clear(&self, color: (f64, f64, f64)) {
        self.gpu.state.lock().unwrap().clear = [
            (color.0 / 255.0) as f32,
            (color.1 / 255.0) as f32,
            (color.2 / 255.0) as f32,
        ];
    }

    fn set_msaa(&self, enabled: bool) {
        self.gpu.set_msaa(enabled);
    }

    fn frame(&self, py: Python<'_>, draw: &Bound<'_, PyAny>) -> PyResult<()> {
        let view = self
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        begin_frame(py, &self.gpu, &self.canvas, view);
        draw.call0()?;
        end_frame(
            py,
            &self.gpu,
            &self.canvas,
            self.width,
            self.height,
            None,
            None,
        );
        Ok(())
    }

    fn read_pixels<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray3<u8>>> {
        let mut enc = self
            .gpu
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("readback"),
            });
        let (buf, bpr) =
            copy_to_buffer(&self.gpu, &mut enc, &self.texture, self.width, self.height);
        self.gpu.queue.submit([enc.finish()]);
        let rb = finish_readback(&self.gpu, &buf, bpr, self.width, self.height, false)
            .map_err(PyRuntimeError::new_err)?;
        PyArray1::from_vec(py, rb.rgba).reshape([self.height as usize, self.width as usize, 4])
    }

    fn save_png(&self, path: &str) -> PyResult<()> {
        let mut enc = self
            .gpu
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("readback"),
            });
        let (buf, bpr) =
            copy_to_buffer(&self.gpu, &mut enc, &self.texture, self.width, self.height);
        self.gpu.queue.submit([enc.finish()]);
        let rb = finish_readback(&self.gpu, &buf, bpr, self.width, self.height, false)
            .map_err(PyRuntimeError::new_err)?;
        write_png(path, rb.width, rb.height, &rb.rgba).map_err(PyRuntimeError::new_err)
    }
}

#[pyfunction]
#[pyo3(signature = (api="auto"))]
fn enumerate_adapters<'py>(py: Python<'py>, api: &str) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let api = Api::parse(api)?;
    let mut out = Vec::new();
    for (name, backends) in api.candidates() {
        let inst = crate::gpu::make_instance(backends, None);
        for a in pollster::block_on(inst.enumerate_adapters(backends)) {
            let info = a.get_info();
            let d = adapter_info_dict(py, &info, name)?;
            let lim = a.limits();
            d.set_item("max_texture_2d", lim.max_texture_dimension_2d)?;
            d.set_item("max_uniform_buffer", lim.max_uniform_buffer_binding_size)?;
            let msaa = a
                .get_texture_format_features(wgpu::TextureFormat::Rgba8Unorm)
                .flags
                .sample_count_supported(4)
                && a.get_texture_format_features(crate::gpu::DEPTH_FORMAT)
                    .flags
                    .sample_count_supported(4);
            d.set_item("msaa4", msaa)?;
            out.push(d);
        }
    }
    Ok(out)
}

#[pyfunction]
fn compiled_backends() -> Vec<&'static str> {
    let b = wgpu::Instance::enabled_backend_features();
    let mut v = Vec::new();
    if b.contains(wgpu::Backends::VULKAN) {
        v.push("vulkan");
    }
    if b.contains(wgpu::Backends::GL) {
        v.push("gl");
    }
    if b.contains(wgpu::Backends::METAL) {
        v.push("metal");
    }
    if b.contains(wgpu::Backends::DX12) {
        v.push("dx12");
    }
    v
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<GpuHandle>()?;
    m.add_class::<WindowCore>()?;
    m.add_class::<OffscreenCore>()?;
    m.add_function(wrap_pyfunction!(enumerate_adapters, m)?)?;
    m.add_function(wrap_pyfunction!(compiled_backends, m)?)?;
    m.add("WGPU_VERSION", "30")?;
    m.add("WINIT_VERSION", "0.30")?;
    Ok(())
}
