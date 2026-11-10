use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use numpy::PyReadonlyArrayDyn;
use pyo3::exceptions::{PyIOError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::pybacked::PyBackedBytes;

use crate::gpu::Gpu;
use crate::renderer::SHADER_UI;

const FLOATS: usize = 20;
const STRIDE: u64 = (FLOATS * 4) as u64;
const ATLAS: u32 = 1024;

pub type Rgba = [f32; 4];

fn parse_color(obj: &Bound<'_, PyAny>) -> PyResult<Rgba> {
    let n = obj.len()?;
    if n != 3 && n != 4 {
        return Err(PyValueError::new_err("color must have 3 or 4 components"));
    }
    let g = |i: usize| -> PyResult<f32> { Ok(obj.get_item(i)?.extract::<f64>()? as f32) };
    Ok([
        g(0)? / 255.0,
        g(1)? / 255.0,
        g(2)? / 255.0,
        if n == 4 { g(3)? / 255.0 } else { 1.0 },
    ])
}

struct FontSet {
    regular: Vec<fontdue::Font>,
    bold: Vec<fontdue::Font>,
    custom: Vec<Vec<fontdue::Font>>,
}

fn load_font(dir: &PathBuf, name: &str) -> Option<fontdue::Font> {
    let bytes = std::fs::read(dir.join(name)).ok()?;
    fontdue::Font::from_bytes(bytes, fontdue::FontSettings::default()).ok()
}

impl FontSet {
    fn load(dir: &PathBuf) -> FontSet {
        let pick = |names: &[&str]| {
            names
                .iter()
                .filter_map(|n| load_font(dir, n))
                .collect::<Vec<_>>()
        };
        let regular = pick(&["Carlito-Regular.ttf", "DejaVuSans.ttf"]);
        let bold = pick(&["Carlito-Bold.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]);
        if regular.is_empty() {
            log::warn!(
                "no UI fonts found in {}; text will not be drawn",
                dir.display()
            );
        }
        FontSet {
            regular,
            bold,
            custom: Vec::new(),
        }
    }

    fn chain(&self, bold: bool, font: u16) -> &[fontdue::Font] {
        if font > 0 {
            if let Some(c) = self.custom.get(font as usize - 1) {
                return c;
            }
        }
        if bold && !self.bold.is_empty() {
            &self.bold
        } else {
            &self.regular
        }
    }
}

#[derive(Clone, Copy)]
struct Glyph {
    adv: f32,
    region: Option<[f32; 8]>,
}

struct Layout {
    rows: Vec<[f32; FLOATS]>,
    width: f32,
    height: f32,
}

struct Atlas {
    texture: wgpu::Texture,
    view: wgpu::TextureView,
    glyphs: HashMap<(char, u32, bool, u16), Glyph>,
    cx: u32,
    cy: u32,
    row_h: u32,
    need_reset: bool,
}

impl Atlas {
    fn new(gpu: &Gpu) -> Atlas {
        let texture = gpu.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("glyph atlas"),
            size: wgpu::Extent3d {
                width: ATLAS,
                height: ATLAS,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let mut a = Atlas {
            texture,
            view,
            glyphs: HashMap::new(),
            cx: 6,
            cy: 0,
            row_h: 0,
            need_reset: false,
        };
        a.reset(gpu);
        a
    }

    fn write(&self, gpu: &Gpu, x: u32, y: u32, w: u32, h: u32, data: &[u8]) {
        gpu.queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d { x, y, z: 0 },
                aspect: wgpu::TextureAspect::All,
            },
            data,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(w * 4),
                rows_per_image: Some(h),
            },
            wgpu::Extent3d {
                width: w,
                height: h,
                depth_or_array_layers: 1,
            },
        );
    }

    fn reset(&mut self, gpu: &Gpu) {
        self.glyphs.clear();
        self.cx = 6;
        self.cy = 0;
        self.row_h = 0;
        self.need_reset = false;
        self.write(gpu, 0, 0, 4, 4, &[255u8; 64]);
    }
}

pub struct TexInner {
    gpu: Arc<Gpu>,
    texture: wgpu::Texture,
    bind_group: wgpu::BindGroup,
    width: u32,
    height: u32,
}

impl TexInner {
    pub fn width(&self) -> u32 {
        self.width
    }

    pub fn height(&self) -> u32 {
        self.height
    }

    pub fn write_rgba(&self, x: u32, y: u32, w: u32, h: u32, data: &[u8]) {
        self.gpu.queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d { x, y, z: 0 },
                aspect: wgpu::TextureAspect::All,
            },
            data,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(w * 4),
                rows_per_image: Some(h),
            },
            wgpu::Extent3d {
                width: w,
                height: h,
                depth_or_array_layers: 1,
            },
        );
    }
}
