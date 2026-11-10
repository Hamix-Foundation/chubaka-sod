use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Instant, SystemTime};

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use wgpu::util::DeviceExt;

use crate::gpu::{Gpu, SceneStats, Timer, DEPTH_FORMAT};
use crate::lighting::{Gathered, Lighting, MAX_LIGHTS};
use crate::mesh::{mesh_by_gid, MeshData};
use crate::object::{camera_rotation, Camera};
use crate::scene::Scene;
use crate::store::{store, COLUMNS, COL_VISIBLE, STRIDE};

pub const SHADER_COMMON: &str = include_str!("shaders/common.wgsl");
pub const SHADER_MAIN: &str = include_str!("shaders/main.wgsl");
pub const SHADER_SHADOW: &str = include_str!("shaders/shadow.wgsl");
pub const SHADER_UI: &str = include_str!("shaders/ui.wgsl");

const GLOBAL_FLOATS: usize = 76 + 12 * MAX_LIGHTS;
const SHADOW_RES: [u32; 3] = [4, 1024, 2048];
const SHADOW_HALF: f64 = 72.0;
const SHADOW_BACK: f64 = 260.0;
const SHADOW_FRONT: f64 = 200.0;

type V3 = [f64; 3];

fn unit(v: V3) -> V3 {
    let l = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
    [v[0] / l, v[1] / l, v[2] / l]
}

fn cross(a: V3, b: V3) -> V3 {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn dot(a: V3, b: V3) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

type M4 = [[f64; 4]; 4];

fn mul4(a: &M4, b: &M4) -> M4 {
    let mut o = [[0.0; 4]; 4];
    for i in 0..4 {
        for j in 0..4 {
            o[i][j] = (0..4).map(|k| a[i][k] * b[k][j]).sum();
        }
    }
    o
}

fn ident4() -> M4 {
    let mut m = [[0.0; 4]; 4];
    for i in 0..4 {
        m[i][i] = 1.0;
    }
    m
}

struct GpuMesh {
    vbuf: wgpu::Buffer,
    ibuf: wgpu::Buffer,
    index_count: u32,
    triangles: usize,
}

struct Shaders {
    main: wgpu::ShaderModule,
    shadow: wgpu::ShaderModule,
}

struct Watch {
    dir: PathBuf,
    stamp: HashMap<&'static str, SystemTime>,
    last_poll: Instant,
}

fn vertex_layouts() -> [wgpu::VertexBufferLayout<'static>; 2] {
    const V: [wgpu::VertexAttribute; 2] = wgpu::vertex_attr_array![0 => Float32x3, 1 => Unorm8x4];
    const I: [wgpu::VertexAttribute; 4] = [
        wgpu::VertexAttribute {
            format: wgpu::VertexFormat::Float32x3,
            offset: 0,
            shader_location: 2,
        },
        wgpu::VertexAttribute {
            format: wgpu::VertexFormat::Unorm8x4,
            offset: 12,
            shader_location: 3,
        },
        wgpu::VertexAttribute {
            format: wgpu::VertexFormat::Float32x4,
            offset: 16,
            shader_location: 4,
        },
        wgpu::VertexAttribute {
            format: wgpu::VertexFormat::Float32x3,
            offset: 32,
            shader_location: 5,
        },
    ];
    [
        wgpu::VertexBufferLayout {
            array_stride: 16,
            step_mode: wgpu::VertexStepMode::Vertex,
            attributes: &V,
        },
        wgpu::VertexBufferLayout {
            array_stride: STRIDE as u64,
            step_mode: wgpu::VertexStepMode::Instance,
            attributes: &I,
        },
    ]
}

#[pyclass(module = "lysyk.engine._native")]
pub struct Renderer {
    gpu: Arc<Gpu>,
    lighting: Py<Lighting>,
    #[pyo3(get, set)]
    shadow_quality: usize,
    #[pyo3(get, set)]
    shadow_half: f64,
    cull: Option<wgpu::Face>,
    front_face: wgpu::FrontFace,
    cull_name: String,
    front_name: String,
    t0: Instant,
    bgl: wgpu::BindGroupLayout,
    sbgl: wgpu::BindGroupLayout,
    layout: wgpu::PipelineLayout,
    slayout: wgpu::PipelineLayout,
    globals: wgpu::Buffer,
    shadow_bg: wgpu::BindGroup,
    sampler: wgpu::Sampler,
    shadow_res: u32,
    shadow_view: Option<wgpu::TextureView>,
    bind_group: Option<wgpu::BindGroup>,
    inst_capacity: usize,
    inst_buf: wgpu::Buffer,
    shaders: Shaders,
    pipelines: HashMap<
        (
            u32,
            wgpu::TextureFormat,
            Option<wgpu::Face>,
            wgpu::FrontFace,
        ),
        wgpu::RenderPipeline,
    >,
    shadow_pipeline: Option<wgpu::RenderPipeline>,
    meshes: HashMap<u32, GpuMesh>,
    g: Vec<f32>,
    lvp: M4,
    world_texel: f64,
    staging: Vec<f32>,
    groups: Vec<(u32, usize, usize)>,
    s_groups: Vec<(u32, usize, usize)>,
    watch: Option<Watch>,
    last_shader_error: Option<String>,
    shader_reloads: u32,
    stats: SceneStats,
}

const SHADER_FILES: [&str; 3] = ["common.wgsl", "main.wgsl", "shadow.wgsl"];

fn compose(common: &str, body: &str) -> String {
    format!("{common}\n{body}")
}

fn make_module(device: &wgpu::Device, label: &str, src: String) -> wgpu::ShaderModule {
    device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some(label),
        source: wgpu::ShaderSource::Wgsl(src.into()),
    })
}

fn parse_face(s: &str) -> PyResult<Option<wgpu::Face>> {
    match s {
        "back" => Ok(Some(wgpu::Face::Back)),
        "front" => Ok(Some(wgpu::Face::Front)),
        "none" => Ok(None),
        _ => Err(PyValueError::new_err(
            "cull must be 'back', 'front' or 'none'",
        )),
    }
}

fn parse_front(s: &str) -> PyResult<wgpu::FrontFace> {
    match s {
        "cw" => Ok(wgpu::FrontFace::Cw),
        "ccw" => Ok(wgpu::FrontFace::Ccw),
        _ => Err(PyValueError::new_err("front_face must be 'cw' or 'ccw'")),
    }
}

impl Renderer {
    fn pipeline_for(
        &self,
        shaders: &Shaders,
        key: (
            u32,
            wgpu::TextureFormat,
            Option<wgpu::Face>,
            wgpu::FrontFace,
        ),
    ) -> wgpu::RenderPipeline {
        let layouts = vertex_layouts();
        self.gpu
            .device
            .create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                label: Some("scene"),
                layout: Some(&self.layout),
                vertex: wgpu::VertexState {
                    module: &shaders.main,
                    entry_point: Some("vs"),
                    compilation_options: Default::default(),
                    buffers: &[Some(layouts[0].clone()), Some(layouts[1].clone())],
                },
                primitive: wgpu::PrimitiveState {
                    topology: wgpu::PrimitiveTopology::TriangleList,
                    cull_mode: key.2,
                    front_face: key.3,
                    ..Default::default()
                },
                depth_stencil: Some(wgpu::DepthStencilState {
                    format: DEPTH_FORMAT,
                    depth_write_enabled: Some(true),
                    depth_compare: Some(wgpu::CompareFunction::Greater),
                    stencil: Default::default(),
                    bias: Default::default(),
                }),
                multisample: wgpu::MultisampleState {
                    count: key.0,
                    mask: !0,
                    alpha_to_coverage_enabled: false,
                },
                fragment: Some(wgpu::FragmentState {
                    module: &shaders.main,
                    entry_point: Some("fs"),
                    compilation_options: Default::default(),
                    targets: &[Some(wgpu::ColorTargetState {
                        format: key.1,
                        blend: None,
                        write_mask: wgpu::ColorWrites::ALL,
                    })],
                }),
                multiview_mask: None,
                cache: None,
            })
    }

    fn shadow_pipeline_for(&self, shaders: &Shaders) -> wgpu::RenderPipeline {
        let layouts = vertex_layouts();
        self.gpu
            .device
            .create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                label: Some("shadow"),
                layout: Some(&self.slayout),
                vertex: wgpu::VertexState {
                    module: &shaders.shadow,
                    entry_point: Some("vs"),
                    compilation_options: Default::default(),
                    buffers: &[Some(layouts[0].clone()), Some(layouts[1].clone())],
                },
                primitive: wgpu::PrimitiveState {
                    topology: wgpu::PrimitiveTopology::TriangleList,
                    cull_mode: None,
                    ..Default::default()
                },
                depth_stencil: Some(wgpu::DepthStencilState {
                    format: DEPTH_FORMAT,
                    depth_write_enabled: Some(true),
                    depth_compare: Some(wgpu::CompareFunction::Less),
                    stencil: Default::default(),
                    bias: Default::default(),
                }),
                multisample: wgpu::MultisampleState::default(),
                fragment: None,
                multiview_mask: None,
                cache: None,
            })
    }

    fn make_shadow(&mut self, res: u32) {
        if res == self.shadow_res && self.shadow_view.is_some() {
            return;
        }
        self.shadow_res = res;
        let tex = self.gpu.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("shadow map"),
            size: wgpu::Extent3d {
                width: res,
                height: res,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: DEPTH_FORMAT,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::TEXTURE_BINDING,
            view_formats: &[],
        });
        let view = tex.create_view(&wgpu::TextureViewDescriptor::default());
        self.bind_group = Some(
            self.gpu
                .device
                .create_bind_group(&wgpu::BindGroupDescriptor {
                    label: Some("globals"),
                    layout: &self.bgl,
                    entries: &[
                        wgpu::BindGroupEntry {
                            binding: 0,
                            resource: self.globals.as_entire_binding(),
                        },
                        wgpu::BindGroupEntry {
                            binding: 1,
                            resource: wgpu::BindingResource::TextureView(&view),
                        },
                        wgpu::BindGroupEntry {
                            binding: 2,
                            resource: wgpu::BindingResource::Sampler(&self.sampler),
                        },
                    ],
                }),
        );
        self.shadow_view = Some(view);
    }

    fn make_instance_buffer(&mut self) {
        self.inst_buf = self.gpu.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("instances"),
            size: (self.inst_capacity * STRIDE) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
    }

    fn gpu_mesh(&mut self, gid: u32) -> Option<&GpuMesh> {
        if !self.meshes.contains_key(&gid) {
            let m: Arc<MeshData> = mesh_by_gid(gid)?;
            let mut vb: Vec<u8> = Vec::with_capacity(m.vertices.len() * 16);
            for (p, c) in m.vertices.iter().zip(m.colors.iter()) {
                for k in 0..3 {
                    vb.extend_from_slice(&p[k].to_le_bytes());
                }
                vb.extend_from_slice(c);
            }
            let idx: Vec<u32> = m.faces.iter().flatten().copied().collect();
            let d = &self.gpu.device;
            let vbuf = d.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("mesh vertices"),
                contents: &vb,
                usage: wgpu::BufferUsages::VERTEX,
            });
            let ibuf = d.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("mesh indices"),
                contents: bytemuck::cast_slice(&idx),
                usage: wgpu::BufferUsages::INDEX,
            });
            self.meshes.insert(
                gid,
                GpuMesh {
                    vbuf,
                    ibuf,
                    index_count: idx.len() as u32,
                    triangles: m.faces.len(),
                },
            );
        }
        self.meshes.get(&gid)
    }

    fn cull_far(&self, fog_density: f64) -> f64 {
        let d = fog_density.max(1e-4);
        (2.35 / d).clamp(350.0, 2600.0)
    }

    fn fit_shadow(&mut self, sun: V3, cam: V3, r: &[[f64; 3]; 3], res: u32) -> (V3, V3, V3, V3) {
        let half = self.shadow_half;
        let f = unit([-sun[0], -sun[1], -sun[2]]);
        let rf: V3 = if f[1].abs() < 0.99 {
            [0.0, 1.0, 0.0]
        } else {
            [0.0, 0.0, 1.0]
        };
        let right = unit(cross(rf, f));
        let up = cross(f, right);
        let fwd = [r[0][2], r[1][2], r[2][2]];
        let mut focus = [
            cam[0] + fwd[0] * half * 0.55,
            0.0,
            cam[2] + fwd[2] * half * 0.55,
        ];
        focus[1] = 0.0;
        let texel = 2.0 * half / res as f64;
        let cx = (dot(focus, right) / texel).floor() * texel;
        let cy = (dot(focus, up) / texel).floor() * texel;
        let cz = dot(focus, f);
        let c = [
            right[0] * cx + up[0] * cy + f[0] * cz,
            right[1] * cx + up[1] * cy + f[1] * cz,
            right[2] * cx + up[2] * cy + f[2] * cz,
        ];
        let zr = SHADOW_BACK + SHADOW_FRONT;
        let mut m = [[0.0; 4]; 4];
        for k in 0..3 {
            m[0][k] = right[k] / half;
            m[1][k] = up[k] / half;
            m[2][k] = f[k] / zr;
        }
        m[0][3] = -dot(right, c) / half;
        m[1][3] = -dot(up, c) / half;
        m[2][3] = (-dot(f, c) + SHADOW_BACK) / zr;
        m[3][3] = 1.0;
        self.lvp = m;
        self.world_texel = texel;
        (c, right, up, f)
    }

    #[allow(clippy::too_many_arguments)]
    fn write_globals(
        &mut self,
        py: Python<'_>,
        lt: &Lighting,
        cam_state: &crate::object::CameraState,
        r: &[[f64; 3]; 3],
        shadow_on: bool,
        lights: &[Gathered],
        res: u32,
    ) {
        let (width, height) = {
            let st = self.gpu.state.lock().unwrap();
            (st.width as f64, st.height as f64)
        };
        let _ = py;
        let cam = cam_state.position;
        let mut view = ident4();
        for i in 0..3 {
            for j in 0..3 {
                view[i][j] = r[j][i];
            }
            view[i][3] = -(r[0][i] * cam[0] + r[1][i] * cam[1] + r[2][i] * cam[2]);
        }
        let focal = 0.5 * height / (cam_state.fov.to_radians() * 0.5).tan();
        let mut proj = [[0.0; 4]; 4];
        proj[0][0] = 2.0 * focal / width;
        proj[1][1] = 2.0 * focal / height;
        proj[2][3] = cam_state.z_near;
        proj[3][2] = 1.0;
        let vp = mul4(&proj, &view);
        let g = &mut self.g;
        for i in 0..4 {
            for j in 0..4 {
                g[j * 4 + i] = vp[i][j] as f32;
                g[16 + j * 4 + i] = self.lvp[i][j] as f32;
            }
        }
        let c = lt.sky_colors();
        let sun = lt.sun_dir();
        let put3 = |g: &mut Vec<f32>, o: usize, v: [f64; 3]| {
            g[o] = v[0] as f32;
            g[o + 1] = v[1] as f32;
            g[o + 2] = v[2] as f32;
        };
        put3(g, 32, cam);
        g[35] = self.t0.elapsed().as_secs_f32();
        put3(g, 36, c.fog);
        g[39] = lt.fog_density as f32;
        put3(g, 40, sun);
        g[43] = 0.0;
        put3(g, 44, c.sun);
        g[47] = if shadow_on { 1.0 } else { 0.0 };
        put3(g, 48, c.sky);
        g[51] = lt.shadow_strength as f32;
        put3(g, 52, c.ground);
        g[55] = 0.0;
        put3(g, 56, c.zenith);
        g[59] = c.stars as f32;
        put3(g, 60, c.horizon);
        g[63] = c.glow as f32;
        g[64] = lights.len() as f32;
        g[65] = lt.exposure as f32;
        g[66] = lt.fog_scatter as f32;
        g[67] = 0.0;
        g[68] = (lt.water_color.0 / 255.0) as f32;
        g[69] = (lt.water_color.1 / 255.0) as f32;
        g[70] = (lt.water_color.2 / 255.0) as f32;
        g[71] = 0.0;
        g[72] = 1.0 / res as f32;
        g[73] = self.world_texel as f32;
        g[74] = if self.shadow_quality >= 2 { 5.0 } else { 1.0 };
        g[75] = 0.0004;
        for (k, l) in lights.iter().enumerate() {
            let o = 76 + 12 * k;
            put3(g, o, l.pos);
            g[o + 3] = l.radius as f32;
            put3(g, o + 4, l.color);
            g[o + 7] = l.intensity as f32;
            match (l.direction, l.cone) {
                (Some(d), Some(cone)) => {
                    put3(g, o + 8, unit(d));
                    g[o + 11] = cone as f32;
                }
                _ => {
                    put3(g, o + 8, [0.0, -1.0, 0.0]);
                    g[o + 11] = -2.0;
                }
            }
        }
        self.gpu
            .queue
            .write_buffer(&self.globals, 0, bytemuck::cast_slice(&self.g));
    }

    fn read_shader(dir: &PathBuf, name: &str) -> Result<String, String> {
        std::fs::read_to_string(dir.join(name))
            .map_err(|e| format!("{}: {e}", dir.join(name).display()))
    }

    fn try_build_shaders(&self, dir: &PathBuf) -> Result<Shaders, String> {
        let common = Self::read_shader(dir, "common.wgsl")?;
        let main = compose(&common, &Self::read_shader(dir, "main.wgsl")?);
        let shadow = compose(&common, &Self::read_shader(dir, "shadow.wgsl")?);
        let device = &self.gpu.device;
        let guard = device.push_error_scope(wgpu::ErrorFilter::Validation);
        let shaders = Shaders {
            main: make_module(device, "main (hot)", main),
            shadow: make_module(device, "shadow (hot)", shadow),
        };
        let (count, format) = {
            let st = self.gpu.state.lock().unwrap();
            (st.sample_count, st.format)
        };
        let _p = self.pipeline_for(&shaders, (count, format, self.cull, self.front_face));
        let _s = self.shadow_pipeline_for(&shaders);
        match pollster::block_on(guard.pop()) {
            None => Ok(shaders),
            Some(e) => Err(e.to_string()),
        }
    }

    fn poll_shaders(&mut self, force: bool) {
        let Some(w) = self.watch.as_mut() else { return };
        if !force && w.last_poll.elapsed().as_secs_f32() < 0.5 {
            return;
        }
        w.last_poll = Instant::now();
        let mut changed = force;
        for name in SHADER_FILES {
            if let Ok(m) = std::fs::metadata(w.dir.join(name)).and_then(|m| m.modified()) {
                if w.stamp.get(name) != Some(&m) {
                    w.stamp.insert(name, m);
                    changed = true;
                }
            }
        }
        if !changed {
            return;
        }
        let dir = w.dir.clone();
        match self.try_build_shaders(&dir) {
            Ok(s) => {
                self.shaders = s;
                self.pipelines.clear();
                self.shadow_pipeline = None;
                self.last_shader_error = None;
                self.shader_reloads += 1;
                log::info!("shaders reloaded from {}", dir.display());
            }
            Err(e) => {
                log::error!("shader reload failed, keeping previous version:\n{e}");
                self.last_shader_error = Some(e);
            }
        }
    }
}

#[pymethods]
impl Renderer {
    #[new]
    fn new(py: Python<'_>, window: &Bound<'_, PyAny>, lighting: Py<Lighting>) -> PyResult<Self> {
        let handle: PyRef<crate::window::GpuHandle> = window.getattr("_gpu")?.extract()?;
        let gpu = handle.gpu.clone();
        let _ = py;
        let device = &gpu.device;
        let both = wgpu::ShaderStages::VERTEX | wgpu::ShaderStages::FRAGMENT;
        let bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("scene bgl"),
            entries: &[
                wgpu::BindGroupLayoutEntry {
                    binding: 0,
                    visibility: both,
                    ty: wgpu::BindingType::Buffer {
                        ty: wgpu::BufferBindingType::Uniform,
                        has_dynamic_offset: false,
                        min_binding_size: None,
                    },
                    count: None,
                },
                wgpu::BindGroupLayoutEntry {
                    binding: 1,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Texture {
                        sample_type: wgpu::TextureSampleType::Depth,
                        view_dimension: wgpu::TextureViewDimension::D2,
                        multisampled: false,
                    },
                    count: None,
                },
                wgpu::BindGroupLayoutEntry {
                    binding: 2,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Comparison),
                    count: None,
                },
            ],
        });
        let sbgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("shadow bgl"),
            entries: &[wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::VERTEX,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    has_dynamic_offset: false,
                    min_binding_size: None,
                },
                count: None,
            }],
        });
        let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("scene layout"),
            bind_group_layouts: &[Some(&bgl)],
            immediate_size: 0,
        });
        let slayout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("shadow layout"),
            bind_group_layouts: &[Some(&sbgl)],
            immediate_size: 0,
        });
        let globals = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("globals"),
            size: (GLOBAL_FLOATS * 4) as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let shadow_bg = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("shadow globals"),
            layout: &sbgl,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: globals.as_entire_binding(),
            }],
        });
        let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("shadow sampler"),
            mag_filter: wgpu::FilterMode::Linear,
            min_filter: wgpu::FilterMode::Linear,
            compare: Some(wgpu::CompareFunction::LessEqual),
            ..Default::default()
        });
        let shaders = Shaders {
            main: make_module(device, "main", compose(SHADER_COMMON, SHADER_MAIN)),
            shadow: make_module(device, "shadow", compose(SHADER_COMMON, SHADER_SHADOW)),
        };
        let inst_capacity = 1024;
        let inst_buf = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("instances"),
            size: (inst_capacity * STRIDE) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let mut r = Renderer {
            gpu,
            lighting,
            shadow_quality: 2,
            shadow_half: SHADOW_HALF,
            cull: Some(wgpu::Face::Back),
            front_face: wgpu::FrontFace::Cw,
            cull_name: "back".into(),
            front_name: "cw".into(),
            t0: Instant::now(),
            bgl,
            sbgl,
            layout,
            slayout,
            globals,
            shadow_bg,
            sampler,
            shadow_res: 0,
            shadow_view: None,
            bind_group: None,
            inst_capacity,
            inst_buf,
            shaders,
            pipelines: HashMap::new(),
            shadow_pipeline: None,
            meshes: HashMap::new(),
            g: vec![0.0; GLOBAL_FLOATS],
            lvp: ident4(),
            world_texel: 1.0,
            staging: Vec::new(),
            groups: Vec::new(),
            s_groups: Vec::new(),
            watch: None,
            last_shader_error: None,
            shader_reloads: 0,
            stats: SceneStats::default(),
        };
        let _ = &r.sbgl;
        r.make_shadow(SHADOW_RES[0]);
        if let Ok(dir) = std::env::var("LYSYK_SHADERS") {
            if !dir.is_empty() {
                r.watch_shaders(Some(dir))?;
            }
        }
        Ok(r)
    }

    #[getter]
    fn cull(&self) -> String {
        self.cull_name.clone()
    }

    #[setter]
    fn set_cull(&mut self, v: &str) -> PyResult<()> {
        self.cull = parse_face(v)?;
        self.cull_name = v.to_string();
        Ok(())
    }

    #[getter]
    fn shadow_quality(&self) -> usize {
        self.shadow_quality
    }

    #[setter]
    fn set_shadow_quality(&mut self, v: usize) {
        self.shadow_quality = v.min(2);
    }

    #[getter]
    fn shadow_range(&self) -> f64 {
        self.shadow_half
    }

    #[setter]
    fn set_shadow_range(&mut self, v: f64) {
        self.shadow_half = v.clamp(2.0, 512.0);
    }

    #[getter]
    fn front_face(&self) -> String {
        self.front_name.clone()
    }

    #[setter]
    fn set_front_face(&mut self, v: &str) -> PyResult<()> {
        self.front_face = parse_front(v)?;
        self.front_name = v.to_string();
        Ok(())
    }

    #[getter]
    fn stats<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        d.set_item("draws", self.stats.draws)?;
        d.set_item("shadow_draws", self.stats.shadow_draws)?;
        d.set_item("objects", self.stats.objects)?;
        d.set_item("visible", self.stats.visible)?;
        d.set_item("shadow_visible", self.stats.shadow_visible)?;
        d.set_item("triangles", self.stats.triangles)?;
        d.set_item("lights", self.stats.lights)?;
        d.set_item("gpu_meshes", self.meshes.len())?;
        d.set_item("instance_capacity", self.inst_capacity)?;
        d.set_item("shader_reloads", self.shader_reloads)?;
        Ok(d)
    }

    #[getter]
    fn shader_error(&self) -> Option<String> {
        self.last_shader_error.clone()
    }

    #[pyo3(signature = (directory=None))]
    fn watch_shaders(&mut self, directory: Option<String>) -> PyResult<()> {
        match directory {
            None => {
                self.watch = None;
                Ok(())
            }
            Some(d) => {
                let dir = PathBuf::from(d);
                if !dir.is_dir() {
                    return Err(PyRuntimeError::new_err(format!(
                        "shader directory not found: {}",
                        dir.display()
                    )));
                }
                for name in SHADER_FILES {
                    if !dir.join(name).is_file() {
                        return Err(PyRuntimeError::new_err(format!(
                            "missing {} in {} (run `python -m lysyk.engine dump-shaders {}`)",
                            name,
                            dir.display(),
                            dir.display()
                        )));
                    }
                }
                self.watch = Some(Watch {
                    dir,
                    stamp: HashMap::new(),
                    last_poll: Instant::now(),
                });
                self.poll_shaders(true);
                Ok(())
            }
        }
    }

    fn reload_shaders(&mut self) {
        self.poll_shaders(true);
    }

    fn render(
        &mut self,
        py: Python<'_>,
        camera: &Bound<'_, Camera>,
        scene: &Bound<'_, Scene>,
    ) -> PyResult<()> {
        let mut timer = Timer::start();
        self.poll_shaders(false);
        let cam_state = camera.borrow().state(py);
        let lt_ref = self.lighting.clone_ref(py);
        let lt = lt_ref.bind(py).borrow();
        let mut sc = scene.borrow_mut();
        sc.rebuild(py)?;
        let entries = sc.entries();
        let r = camera_rotation(
            cam_state.rotation[0],
            cam_state.rotation[1],
            cam_state.rotation[2],
        );
        let cam = cam_state.position;
        let (width, height, sample_count, format) = {
            let st = self.gpu.state.lock().unwrap();
            (
                st.width as f64,
                st.height as f64,
                st.sample_count,
                st.format,
            )
        };
        let focal = 0.5 * height / (cam_state.fov.to_radians() * 0.5).tan();
        let tx = width / (2.0 * focal);
        let ty = height / (2.0 * focal);
        let (nx, ny) = ((1.0 + tx * tx).sqrt(), (1.0 + ty * ty).sqrt());
        let far = self.cull_far(lt.fog_density);
        let near = cam_state.z_near;
        let s = store();

        let shadow_on = lt.shadows && self.shadow_quality > 0;
        let res = if shadow_on {
            SHADOW_RES[self.shadow_quality.min(2)]
        } else {
            SHADOW_RES[0]
        };
        self.make_shadow(res);
        let basis = if shadow_on {
            Some(self.fit_shadow(lt.sun_dir(), cam, &r, res))
        } else {
            self.lvp = ident4();
            self.world_texel = 1.0;
            None
        };

        self.staging.clear();
        self.groups.clear();
        self.s_groups.clear();
        let mut s_rows: Vec<f32> = Vec::new();
        let mut visible = 0usize;
        let mut triangles = 0usize;
        let half = self.shadow_half;
        let mut tri_cache: HashMap<u32, usize> = HashMap::new();

        let push =
            |buf: &mut Vec<f32>, groups: &mut Vec<(u32, usize, usize)>, gid: u32, row: &[f32]| {
                let n = buf.len() / COLUMNS;
                match groups.last_mut() {
                    Some(g) if g.0 == gid => g.2 += 1,
                    _ => groups.push((gid, n, 1)),
                }
                buf.extend_from_slice(row);
            };

        for e in entries {
            let row = s.row(e.slot);
            if row[COL_VISIBLE] <= 0.5 {
                continue;
            }
            let pos = [row[0] as f64, row[1] as f64, row[2] as f64];
            let scl = [row[8] as f64, row[9] as f64, row[10] as f64];
            let rotated = row[4] != 0.0 || row[5] != 0.0 || row[6] != 0.0;
            let wc = if rotated {
                pos
            } else {
                [
                    pos[0] + e.center[0] as f64 * scl[0],
                    pos[1] + e.center[1] as f64 * scl[1],
                    pos[2] + e.center[2] as f64 * scl[2],
                ]
            };
            let rad = (if rotated { e.ro } else { e.rc }) as f64 * scl[0].max(scl[1]).max(scl[2]);
            let d = [wc[0] - cam[0], wc[1] - cam[1], wc[2] - cam[2]];
            let v = [
                d[0] * r[0][0] + d[1] * r[1][0] + d[2] * r[2][0],
                d[0] * r[0][1] + d[1] * r[1][1] + d[2] * r[2][1],
                d[0] * r[0][2] + d[1] * r[1][2] + d[2] * r[2][2],
            ];
            let z = v[2];
            if z + rad > near
                && v[0].abs() <= tx * z + rad * nx
                && v[1].abs() <= ty * z + rad * ny
                && v[0] * v[0] + v[1] * v[1] + v[2] * v[2] <= (far + rad) * (far + rad)
            {
                push(&mut self.staging, &mut self.groups, e.gid, row);
                visible += 1;
                let t = *tri_cache
                    .entry(e.gid)
                    .or_insert_with(|| mesh_by_gid(e.gid).map_or(0, |m| m.faces.len()));
                triangles += t;
            }
            if let Some((c, right, up, f)) = basis {
                if e.cast {
                    let rel = [wc[0] - c[0], wc[1] - c[1], wc[2] - c[2]];
                    let lx = dot(rel, right);
                    let ly = dot(rel, up);
                    let lz = dot(rel, f);
                    if lx.abs() <= half + rad
                        && ly.abs() <= half + rad
                        && lz + rad >= -SHADOW_BACK
                        && lz - rad <= SHADOW_FRONT
                    {
                        push(&mut s_rows, &mut self.s_groups, e.gid, row);
                    }
                }
            }
        }
        let n_main = self.staging.len() / COLUMNS;
        let n_shadow = s_rows.len() / COLUMNS;
        self.staging.extend_from_slice(&s_rows);
        let objects = entries.len();
        drop(sc);
        self.gpu.profiler.add(2, timer.lap());

        let total = n_main + n_shadow;
        if total > 0 {
            if total > self.inst_capacity {
                while self.inst_capacity < total {
                    self.inst_capacity *= 2;
                }
                self.make_instance_buffer();
            }
            self.gpu
                .queue
                .write_buffer(&self.inst_buf, 0, bytemuck::cast_slice(&self.staging));
        }
        let lights = lt.gather_lights(py, cam);
        self.write_globals(py, &lt, &cam_state, &r, shadow_on, &lights, res);
        drop(lt);

        let key = (sample_count, format, self.cull, self.front_face);
        if !self.pipelines.contains_key(&key) {
            let p = self.pipeline_for(&self.shaders, key);
            self.pipelines.insert(key, p);
        }
        if shadow_on && self.shadow_pipeline.is_none() {
            self.shadow_pipeline = Some(self.shadow_pipeline_for(&self.shaders));
        }
        let ids: Vec<u32> = self
            .groups
            .iter()
            .chain(self.s_groups.iter())
            .map(|g| g.0)
            .collect();
        for gid in ids {
            self.gpu_mesh(gid);
        }
        self.gpu.profiler.add(3, timer.lap());

        let gpu = self.gpu.clone();
        let mut st = gpu.state.lock().unwrap();
        if st.encoder.is_none() {
            return Err(PyRuntimeError::new_err(
                "Renderer.render() must be called from on_draw()",
            ));
        }
        if shadow_on {
            let enc = st.encoder.as_mut().unwrap();
            let mut sp = enc.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("shadow"),
                color_attachments: &[],
                depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                    view: self.shadow_view.as_ref().unwrap(),
                    depth_ops: Some(wgpu::Operations {
                        load: wgpu::LoadOp::Clear(1.0),
                        store: wgpu::StoreOp::Store,
                    }),
                    stencil_ops: None,
                }),
                timestamp_writes: None,
                occlusion_query_set: None,
                multiview_mask: None,
            });
            if !self.s_groups.is_empty() {
                sp.set_pipeline(self.shadow_pipeline.as_ref().unwrap());
                sp.set_bind_group(0, &self.shadow_bg, &[]);
                draw(
                    &mut sp,
                    &self.meshes,
                    &self.inst_buf,
                    &self.s_groups,
                    n_main,
                );
            }
        }
        gpu.profiler.add(4, timer.lap());
        {
            let device = &gpu.device;
            if let Some(mut rp) = st.begin_scene_pass(device) {
                if !self.groups.is_empty() {
                    rp.set_pipeline(&self.pipelines[&key]);
                    rp.set_bind_group(0, self.bind_group.as_ref().unwrap(), &[]);
                    draw(&mut rp, &self.meshes, &self.inst_buf, &self.groups, 0);
                }
            }
        }
        gpu.profiler.add(5, timer.lap());
        self.stats = SceneStats {
            draws: self.groups.len(),
            shadow_draws: self.s_groups.len(),
            objects,
            visible,
            shadow_visible: n_shadow,
            triangles,
            lights: lights.len(),
        };
        st.scene_stats = self.stats;
        Ok(())
    }
}

fn draw(
    rp: &mut wgpu::RenderPass<'_>,
    meshes: &HashMap<u32, GpuMesh>,
    inst: &wgpu::Buffer,
    groups: &[(u32, usize, usize)],
    base: usize,
) {
    for &(gid, start, count) in groups {
        let Some(m) = meshes.get(&gid) else { continue };
        rp.set_vertex_buffer(0, m.vbuf.slice(..));
        rp.set_vertex_buffer(1, inst.slice(((base + start) * STRIDE) as u64..));
        rp.set_index_buffer(m.ibuf.slice(..), wgpu::IndexFormat::Uint32);
        rp.draw_indexed(0..m.index_count, 0, 0..count as u32);
        let _ = m.triangles;
    }
}

#[pyfunction]
pub fn shader_sources() -> Vec<(String, String)> {
    vec![
        ("common.wgsl".into(), SHADER_COMMON.into()),
        ("main.wgsl".into(), SHADER_MAIN.into()),
        ("shadow.wgsl".into(), SHADER_SHADOW.into()),
        ("ui.wgsl".into(), SHADER_UI.into()),
    ]
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Renderer>()?;
    m.add_function(wrap_pyfunction!(shader_sources, m)?)?;
    Ok(())
}
