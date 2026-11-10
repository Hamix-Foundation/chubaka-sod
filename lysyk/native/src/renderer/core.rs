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

pub const SHADER_COMMON: &str = include_str!("../shaders/common.wgsl");
pub const SHADER_MAIN: &str = include_str!("../shaders/main.wgsl");
pub const SHADER_SHADOW: &str = include_str!("../shaders/shadow.wgsl");
pub const SHADER_UI: &str = include_str!("../shaders/ui.wgsl");

const GLOBAL_FLOATS: usize = 76 + 12 * MAX_LIGHTS;
const SHADOW_RES: [u32; 4] = [4, 1024, 2048, 2560];
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
    triangle_cache: HashMap<u32, usize>,
    g: Vec<f32>,
    lvp: M4,
    world_texel: f64,
    staging: Vec<f32>,
    shadow_staging: Vec<f32>,
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
