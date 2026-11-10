use std::sync::{Arc, Mutex};
use std::time::Instant;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

pub const DEPTH_FORMAT: wgpu::TextureFormat = wgpu::TextureFormat::Depth32Float;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Api {
    Auto,
    Vulkan,
    Gl,
    #[cfg(target_os = "windows")]
    Dx12,
}

impl Api {
    pub fn parse(s: &str) -> PyResult<Api> {
        match s.trim().to_ascii_lowercase().as_str() {
            "" | "auto" => Ok(Api::Auto),
            "vulkan" | "vk" => Ok(Api::Vulkan),
            "gl" | "opengl" | "gles" | "opengles" => Ok(Api::Gl),
            "dx12" | "directx" | "direct3d12" => {
                #[cfg(target_os = "windows")]
                { Ok(Api::Dx12) }
                #[cfg(not(target_os = "windows"))]
                { Err(PyRuntimeError::new_err("DirectX 12 is only available on Windows")) }
            }
            other => Err(PyRuntimeError::new_err(format!(
                "unknown graphics API '{other}' (use auto, vulkan or gl)"
            ))),
        }
    }

    pub fn candidates(self) -> Vec<(&'static str, wgpu::Backends)> {
        let mut v = Vec::new();
        if matches!(self, Api::Auto | Api::Vulkan)
            && wgpu::Instance::enabled_backend_features().contains(wgpu::Backends::VULKAN)
        {
            v.push(("Vulkan", wgpu::Backends::VULKAN));
        }
        #[cfg(target_os = "windows")]
        if matches!(self, Api::Dx12) && wgpu::Instance::enabled_backend_features().contains(wgpu::Backends::DX12) {
            v.push(("Direct3D 12", wgpu::Backends::DX12));
        }
        if matches!(self, Api::Auto | Api::Gl)
            && wgpu::Instance::enabled_backend_features().contains(wgpu::Backends::GL)
        {
            v.push(("OpenGL", wgpu::Backends::GL));
        }
        #[cfg(any(target_os = "macos", target_os = "ios"))]
        if self == Api::Auto {
            v.insert(0, ("Metal", wgpu::Backends::METAL));
        }
        #[cfg(target_os = "windows")]
        if self == Api::Auto {
            v.push(("Direct3D 12", wgpu::Backends::DX12));
        }
        v
    }
}

pub const STAGES: [&str; 9] = [
    "update", "draw", "cull", "upload", "shadow", "scene", "ui", "submit", "present",
];

#[derive(Clone, Copy, Default)]
pub struct FrameRecord {
    pub total: f32,
    pub stages: [f32; STAGES.len()],
}

pub struct ProfilerInner {
    pub ring: Vec<FrameRecord>,
    pub head: usize,
    pub filled: usize,
    pub current: FrameRecord,
    pub frame_start: Option<Instant>,
    pub frames: u64,
}

pub const RING: usize = 240;

pub struct Profiler {
    pub inner: Mutex<ProfilerInner>,
}

impl Profiler {
    pub fn new() -> Self {
        Profiler {
            inner: Mutex::new(ProfilerInner {
                ring: vec![FrameRecord::default(); RING],
                head: 0,
                filled: 0,
                current: FrameRecord::default(),
                frame_start: None,
                frames: 0,
            }),
        }
    }

    pub fn begin(&self) {
        let mut p = self.inner.lock().unwrap();
        p.current = FrameRecord::default();
        p.frame_start = Some(Instant::now());
    }

    pub fn add(&self, stage: usize, ms: f32) {
        self.inner.lock().unwrap().current.stages[stage] += ms;
    }

    pub fn end(&self) {
        let mut p = self.inner.lock().unwrap();
        if let Some(t) = p.frame_start.take() {
            p.current.total = t.elapsed().as_secs_f32() * 1000.0;
        }
        let head = p.head;
        let rec = p.current;
        p.ring[head] = rec;
        p.head = (head + 1) % RING;
        p.filled = (p.filled + 1).min(RING);
        p.frames += 1;
    }

    pub fn history(&self) -> Vec<FrameRecord> {
        let p = self.inner.lock().unwrap();
        let mut out = Vec::with_capacity(p.filled);
        let start = (p.head + RING - p.filled) % RING;
        for i in 0..p.filled {
            out.push(p.ring[(start + i) % RING]);
        }
        out
    }
}

pub struct Timer(Instant);

impl Timer {
    pub fn start() -> Timer {
        Timer(Instant::now())
    }

    pub fn lap(&mut self) -> f32 {
        let now = Instant::now();
        let ms = (now - self.0).as_secs_f32() * 1000.0;
        self.0 = now;
        ms
    }
}

#[derive(Default, Clone, Copy)]
pub struct SceneStats {
    pub draws: usize,
    pub shadow_draws: usize,
    pub objects: usize,
    pub visible: usize,
    pub shadow_visible: usize,
    pub triangles: usize,
    pub lights: usize,
}

pub struct FrameState {
    pub format: wgpu::TextureFormat,
    pub sample_count: u32,
    pub msaa_supported: bool,
    pub width: u32,
    pub height: u32,
    pub clear: [f32; 3],
    pub encoder: Option<wgpu::CommandEncoder>,
    pub frame_view: Option<wgpu::TextureView>,
    pub pass_recorded: bool,
    msaa_view: Option<wgpu::TextureView>,
    depth_view: Option<wgpu::TextureView>,
    att_size: (u32, u32, u32),
    pub scene_stats: SceneStats,
    pub epoch: u64,
}

pub struct Gpu {
    pub instance: wgpu::Instance,
    pub adapter: wgpu::Adapter,
    pub device: wgpu::Device,
    pub queue: wgpu::Queue,
    pub info: wgpu::AdapterInfo,
    pub api_name: &'static str,
    pub state: Mutex<FrameState>,
    pub profiler: Profiler,
    pub dev_message: Mutex<Option<String>>,
    pub screenshot: Mutex<Option<String>>,
}

pub fn adapter_rank(t: wgpu::DeviceType) -> u8 {
    match t {
        wgpu::DeviceType::DiscreteGpu => 0,
        wgpu::DeviceType::IntegratedGpu => 1,
        wgpu::DeviceType::VirtualGpu => 2,
        wgpu::DeviceType::Other => 3,
        wgpu::DeviceType::Cpu => 4,
    }
}

pub fn backend_label(b: wgpu::Backend) -> &'static str {
    match b {
        wgpu::Backend::Vulkan => "Vulkan",
        wgpu::Backend::Gl => "OpenGL",
        wgpu::Backend::Metal => "Metal",
        wgpu::Backend::Dx12 => "Direct3D 12",
        wgpu::Backend::BrowserWebGpu => "WebGPU",
        _ => "Other",
    }
}

pub fn make_instance(
    backends: wgpu::Backends,
    display: Option<Box<dyn wgpu::wgt::WgpuHasDisplayHandle>>,
) -> wgpu::Instance {
    let mut desc = match display {
        Some(d) => wgpu::InstanceDescriptor::new_with_display_handle(d),
        None => wgpu::InstanceDescriptor::new_without_display_handle(),
    };
    desc.backends = backends;
    wgpu::Instance::new(desc)
}

pub type DisplayFactory<'a> = &'a dyn Fn() -> Option<Box<dyn wgpu::wgt::WgpuHasDisplayHandle>>;
pub type SurfaceFactory<'a> = &'a dyn Fn(&wgpu::Instance) -> Option<wgpu::Surface<'static>>;

pub struct Opened {
    pub gpu: Arc<Gpu>,
    pub surface: Option<wgpu::Surface<'static>>,
}

pub fn open(
    api: Api,
    msaa: bool,
    width: u32,
    height: u32,
    display: DisplayFactory,
    make_surface: Option<SurfaceFactory>,
) -> PyResult<Opened> {
    let mut errors: Vec<String> = Vec::new();
    for (name, backends) in api.candidates() {
        let instance = make_instance(backends, display());
        let surface = make_surface.and_then(|f| f(&instance));
        let adapters = pollster::block_on(instance.enumerate_adapters(backends));
        let mut pool: Vec<wgpu::Adapter> = adapters
            .into_iter()
            .filter(|a| surface.as_ref().map_or(true, |s| a.is_surface_supported(s)))
            .collect();
        pool.sort_by_key(|a| adapter_rank(a.get_info().device_type));
        if pool.is_empty() {
            errors.push(format!("{name}: no suitable adapters"));
            continue;
        }
        for adapter in pool {
            let info = adapter.get_info();
            let limits =
                wgpu::Limits::downlevel_webgl2_defaults().using_resolution(adapter.limits());
            let desc = wgpu::DeviceDescriptor {
                label: Some("lysyk"),
                required_features: if info.backend == wgpu::Backend::Vulkan
                    && adapter
                        .features()
                        .contains(wgpu::Features::EXPERIMENTAL_RAY_QUERY)
                {
                    wgpu::Features::EXPERIMENTAL_RAY_QUERY
                } else {
                    wgpu::Features::empty()
                },
                required_limits: limits,
                ..Default::default()
            };
            match pollster::block_on(adapter.request_device(&desc)) {
                Ok((device, queue)) => {
                    log::info!(
                        "graphics: {} / {} ({:?})",
                        name,
                        info.name,
                        info.device_type
                    );
                    let format = pick_format(&adapter, surface.as_ref());
                    let msaa_ok = format_supports_msaa(&adapter, format)
                        && format_supports_msaa(&adapter, DEPTH_FORMAT);
                    let gpu = Gpu {
                        instance,
                        adapter,
                        device,
                        queue,
                        info,
                        api_name: name,
                        state: Mutex::new(FrameState {
                            format,
                            sample_count: if msaa && msaa_ok { 4 } else { 1 },
                            msaa_supported: msaa_ok,
                            width,
                            height,
                            clear: [0.0; 3],
                            encoder: None,
                            frame_view: None,
                            pass_recorded: false,
                            msaa_view: None,
                            depth_view: None,
                            att_size: (0, 0, 0),
                            scene_stats: SceneStats::default(),
                            epoch: 0,
                        }),
                        profiler: Profiler::new(),
                        dev_message: Mutex::new(None),
                        screenshot: Mutex::new(None),
                    };
                    return Ok(Opened {
                        gpu: Arc::new(gpu),
                        surface,
                    });
                }
                Err(e) => errors.push(format!("{name} / {}: {e}", info.name)),
            }
        }
    }
    Err(PyRuntimeError::new_err(format!(
        "no usable graphics device: {}",
        errors.join("; ")
    )))
}

fn format_supports_msaa(adapter: &wgpu::Adapter, f: wgpu::TextureFormat) -> bool {
    adapter
        .get_texture_format_features(f)
        .flags
        .sample_count_supported(4)
}

pub fn pick_format(
    adapter: &wgpu::Adapter,
    surface: Option<&wgpu::Surface<'static>>,
) -> wgpu::TextureFormat {
    let Some(surface) = surface else {
        return wgpu::TextureFormat::Rgba8Unorm;
    };
    let caps = surface.get_capabilities(adapter);
    let non_srgb: Vec<_> = caps
        .formats
        .iter()
        .copied()
        .filter(|f| !f.is_srgb())
        .collect();
    for want in [
        wgpu::TextureFormat::Bgra8Unorm,
        wgpu::TextureFormat::Rgba8Unorm,
    ] {
        if non_srgb.contains(&want) {
            return want;
        }
    }
    non_srgb
        .first()
        .copied()
        .or_else(|| caps.formats.first().copied())
        .unwrap_or(wgpu::TextureFormat::Bgra8Unorm)
}

impl Gpu {
    pub fn configure_surface(
        &self,
        surface: &wgpu::Surface<'static>,
        width: u32,
        height: u32,
        vsync: bool,
    ) -> wgpu::TextureFormat {
        let caps = surface.get_capabilities(&self.adapter);
        let format = pick_format(&self.adapter, Some(surface));
        let mut cfg = surface
            .get_default_config(&self.adapter, width.max(1), height.max(1))
            .expect("surface unsupported by adapter");
        cfg.format = format;
        cfg.usage = wgpu::TextureUsages::RENDER_ATTACHMENT;
        if caps.usages.contains(wgpu::TextureUsages::COPY_SRC) {
            cfg.usage |= wgpu::TextureUsages::COPY_SRC;
        }
        let has = |m: wgpu::PresentMode| caps.present_modes.contains(&m);
        cfg.present_mode = if vsync {
            wgpu::PresentMode::Fifo
        } else if has(wgpu::PresentMode::Immediate) {
            wgpu::PresentMode::Immediate
        } else if has(wgpu::PresentMode::Mailbox) {
            wgpu::PresentMode::Mailbox
        } else {
            wgpu::PresentMode::Fifo
        };
        cfg.desired_maximum_frame_latency = 2;
        surface.configure(&self.device, &cfg);
        let mut st = self.state.lock().unwrap();
        if st.format != format {
            st.format = format;
            st.epoch += 1;
        }
        st.width = cfg.width;
        st.height = cfg.height;
        st.att_size = (0, 0, 0);
        format
    }

    pub fn set_msaa(&self, enabled: bool) {
        let mut st = self.state.lock().unwrap();
        let count = if enabled && st.msaa_supported { 4 } else { 1 };
        if count != st.sample_count {
            st.sample_count = count;
            st.att_size = (0, 0, 0);
            st.epoch += 1;
        }
    }
}

impl FrameState {
    pub fn ensure_attachments(&mut self, device: &wgpu::Device) {
        let key = (self.width, self.height, self.sample_count);
        if self.att_size == key {
            return;
        }
        self.att_size = key;
        let size = wgpu::Extent3d {
            width: self.width.max(1),
            height: self.height.max(1),
            depth_or_array_layers: 1,
        };
        let mk = |format, label| {
            device
                .create_texture(&wgpu::TextureDescriptor {
                    label: Some(label),
                    size,
                    mip_level_count: 1,
                    sample_count: self.sample_count,
                    dimension: wgpu::TextureDimension::D2,
                    format,
                    usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
                    view_formats: &[],
                })
                .create_view(&wgpu::TextureViewDescriptor::default())
        };
        self.depth_view = Some(mk(DEPTH_FORMAT, "depth"));
        self.msaa_view = if self.sample_count > 1 {
            Some(mk(self.format, "msaa"))
        } else {
            None
        };
    }

    pub fn begin_scene_pass<'e>(
        &'e mut self,
        device: &wgpu::Device,
    ) -> Option<wgpu::RenderPass<'e>> {
        self.ensure_attachments(device);
        let c = self.clear;
        let clear = wgpu::Color {
            r: c[0] as f64,
            g: c[1] as f64,
            b: c[2] as f64,
            a: 1.0,
        };
        self.pass_recorded = true;
        let frame = self.frame_view.as_ref()?;
        let (view, resolve, store) = match &self.msaa_view {
            Some(m) => (m, Some(frame), wgpu::StoreOp::Discard),
            None => (frame, None, wgpu::StoreOp::Store),
        };
        let depth = self.depth_view.as_ref()?;
        let enc = self.encoder.as_mut()?;
        Some(enc.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("scene"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view,
                depth_slice: None,
                resolve_target: resolve,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Clear(clear),
                    store,
                },
            })],
            depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                view: depth,
                depth_ops: Some(wgpu::Operations {
                    load: wgpu::LoadOp::Clear(0.0),
                    store: wgpu::StoreOp::Discard,
                }),
                stencil_ops: None,
            }),
            timestamp_writes: None,
            occlusion_query_set: None,
            multiview_mask: None,
        }))
    }
}
