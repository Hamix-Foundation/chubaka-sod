use std::fs::File;
use std::io::BufWriter;

use numpy::{PyArray3, PyArrayMethods, PyUntypedArrayMethods};
use pyo3::exceptions::{PyIOError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;

use crate::canvas::Canvas;
use crate::gpu::{Gpu, STAGES};
use crate::mesh::registry_stats;
use crate::store::store;

fn c(r: u8, g: u8, b: u8, a: u8) -> [f32; 4] {
    [r as f32 / 255.0, g as f32 / 255.0, b as f32 / 255.0, a as f32 / 255.0]
}

pub fn draw_overlay(canvas: &mut Canvas, gpu: &Gpu, w: f32, h: f32, fps: f64) {
    let s = (h / 720.0).max(0.6);
    let hist = gpu.profiler.history();
    let n = hist.len().max(1);
    let avg = hist.iter().map(|r| r.total).sum::<f32>() / n as f32;
    let max = hist.iter().map(|r| r.total).fold(0.0f32, f32::max);
    let mut sorted: Vec<f32> = hist.iter().map(|r| r.total).collect();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let p99 = if sorted.is_empty() { 0.0 } else { sorted[((sorted.len() as f32 * 0.99) as usize).min(sorted.len() - 1)] };
    let st = gpu.state.lock().unwrap().scene_stats;
    let (meshes, verts, tris) = registry_stats();
    let _ = w;

    let x = 12.0 * s;
    let y = 12.0 * s;
    let pw = 360.0 * s;
    let ph = 318.0 * s;
    canvas.rect_c(x, y, pw, ph, c(10, 10, 10, 232), 4.0 * s, Some(c(18, 18, 18, 232)));
    canvas.outline_c(x, y, pw, ph, c(255, 255, 255, 30), 4.0 * s, 1.0);

    let text = c(236, 242, 252, 255);
    let dim = c(160, 160, 160, 255);
    let accent = c(190, 36, 36, 255);
    let mut ty = y + 8.0 * s;
    let fs = 10.0 * s as f64;
    canvas.text_c(&format!("{} · {}", gpu.api_name, gpu.info.name), x + 10.0 * s, ty, accent, fs, 0, 0, true, false);
    ty += 17.0 * s;
    canvas.text_c(
        &format!("{fps:.0} FPS   avg {avg:.2} ms   p99 {p99:.2}   max {max:.2}"),
        x + 10.0 * s, ty, text, fs, 0, 0, false, false,
    );
    ty += 18.0 * s;

    let gx = x + 10.0 * s;
    let gw = pw - 20.0 * s;
    let gh = 62.0 * s;
    let top = (max.max(33.4) * 1.05).min(100.0);
    canvas.rect_c(gx, ty, gw, gh, c(255, 255, 255, 14), 3.0 * s, None);
    let bar_w = gw / crate::gpu::RING as f32;
    for (i, r) in hist.iter().enumerate() {
        let hh = (r.total / top).min(1.0) * gh;
        let col = if r.total <= 16.8 { c(96, 224, 150, 220) } else if r.total <= 33.4 { c(255, 206, 84, 220) } else { c(255, 100, 112, 230) };
        canvas.rect_c(gx + i as f32 * bar_w, ty + gh - hh, (bar_w - 0.5).max(1.0), hh.max(1.0), col, 0.0, None);
    }
    for (ms, label) in [(16.67f32, "16.7"), (33.33, "33.3")] {
        let ly = ty + gh - (ms / top).min(1.0) * gh;
        canvas.rect_c(gx, ly, gw, 1.0, c(255, 255, 255, 70), 0.0, None);
        canvas.text_c(label, gx + gw - 2.0, ly - 10.0 * s, dim, 8.0 * s as f64, 2, 0, false, false);
    }
    ty += gh + 8.0 * s;

    let recent = hist.len().min(60).max(1);
    let tail = &hist[hist.len() - recent.min(hist.len())..];
    let scale = (top / 3.0).max(5.0);
    for (k, name) in STAGES.iter().enumerate() {
        let v = if tail.is_empty() { 0.0 } else { tail.iter().map(|r| r.stages[k]).sum::<f32>() / tail.len() as f32 };
        canvas.text_c(name, gx, ty, dim, 9.0 * s as f64, 0, 0, false, false);
        let bw = 150.0 * s;
        let bx = gx + 66.0 * s;
        canvas.rect_c(bx, ty + 3.0 * s, bw, 6.0 * s, c(255, 255, 255, 22), 3.0 * s, None);
        canvas.rect_c(bx, ty + 3.0 * s, (bw * (v / scale).min(1.0)).max(1.0), 6.0 * s, accent, 3.0 * s, None);
        canvas.text_c(&format!("{v:.2} ms"), bx + bw + 8.0 * s, ty, text, 9.0 * s as f64, 0, 0, false, false);
        ty += 14.0 * s;
    }
    ty += 4.0 * s;
    canvas.text_c(
        &format!("objects {}/{}   draws {}+{}   lights {}", st.visible, st.objects, st.draws, st.shadow_draws, st.lights),
        gx, ty, text, fs, 0, 0, false, false,
    );
    ty += 15.0 * s;
    canvas.text_c(
        &format!("triangles {}   shadow casters {}", fmt_num(st.triangles), st.shadow_visible),
        gx, ty, text, fs, 0, 0, false, false,
    );
    ty += 15.0 * s;
    canvas.text_c(
        &format!("meshes {}  ·  {} verts  ·  {} tris  ·  slots {}", meshes, fmt_num(verts), fmt_num(tris), store().live_slots()),
        gx, ty, dim, 9.0 * s as f64, 0, 0, false, false,
    );
    ty += 14.0 * s;
    let msg = gpu.dev_message.lock().unwrap().clone();
    if let Some(m) = msg {
        let first = m.lines().next().unwrap_or("");
        let short: String = first.chars().take(58).collect();
        canvas.text_c(&short, gx, ty, c(255, 120, 130, 255), 9.0 * s as f64, 0, 0, false, false);
    } else {
        canvas.text_c("F3 overlay · F12 screenshot", gx, ty, dim, 9.0 * s as f64, 0, 0, false, false);
    }
}

fn fmt_num(n: usize) -> String {
    if n >= 1_000_000 {
        format!("{:.2}M", n as f64 / 1e6)
    } else if n >= 1000 {
        format!("{:.1}k", n as f64 / 1e3)
    } else {
        n.to_string()
    }
}

pub struct Readback {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

pub fn copy_to_buffer(gpu: &Gpu, encoder: &mut wgpu::CommandEncoder, tex: &wgpu::Texture, w: u32, h: u32) -> (wgpu::Buffer, u32) {
    let bpr = (w * 4 + 255) / 256 * 256;
    let buf = gpu.device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("readback"),
        size: (bpr * h) as u64,
        usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
        mapped_at_creation: false,
    });
    encoder.copy_texture_to_buffer(
        wgpu::TexelCopyTextureInfo { texture: tex, mip_level: 0, origin: wgpu::Origin3d::ZERO, aspect: wgpu::TextureAspect::All },
        wgpu::TexelCopyBufferInfo { buffer: &buf, layout: wgpu::TexelCopyBufferLayout { offset: 0, bytes_per_row: Some(bpr), rows_per_image: Some(h) } },
        wgpu::Extent3d { width: w, height: h, depth_or_array_layers: 1 },
    );
    (buf, bpr)
}

pub fn finish_readback(gpu: &Gpu, buf: &wgpu::Buffer, bpr: u32, w: u32, h: u32, bgra: bool) -> Result<Readback, String> {
    let slice = buf.slice(..);
    let (tx, rx) = std::sync::mpsc::channel();
    slice.map_async(wgpu::MapMode::Read, move |r| {
        let _ = tx.send(r);
    });
    gpu.device.poll(wgpu::PollType::wait_indefinitely()).map_err(|e| e.to_string())?;
    rx.recv().map_err(|e| e.to_string())?.map_err(|e| e.to_string())?;
    let data = slice.get_mapped_range().map_err(|e| e.to_string())?;
    let mut out = vec![0u8; (w * h * 4) as usize];
    for y in 0..h as usize {
        let src = &data[y * bpr as usize..y * bpr as usize + (w * 4) as usize];
        let dst = &mut out[y * (w * 4) as usize..(y + 1) * (w * 4) as usize];
        if bgra {
            for (d, s) in dst.chunks_exact_mut(4).zip(src.chunks_exact(4)) {
                d.copy_from_slice(&[s[2], s[1], s[0], s[3]]);
            }
        } else {
            dst.copy_from_slice(src);
        }
    }
    drop(data);
    buf.unmap();
    Ok(Readback { width: w, height: h, rgba: out })
}

pub fn write_png(path: &str, w: u32, h: u32, rgba: &[u8]) -> Result<(), String> {
    let file = File::create(path).map_err(|e| format!("{path}: {e}"))?;
    let mut enc = png::Encoder::new(BufWriter::new(file), w, h);
    enc.set_color(png::ColorType::Rgba);
    enc.set_depth(png::BitDepth::Eight);
    let mut writer = enc.write_header().map_err(|e| e.to_string())?;
    writer.write_image_data(rgba).map_err(|e| e.to_string())
}

#[pyfunction]
fn save_png(path: &str, pixels: &Bound<'_, PyArray3<u8>>) -> PyResult<()> {
    let shape = pixels.shape();
    if shape.len() != 3 || shape[2] != 4 {
        return Err(PyValueError::new_err("expected an (H, W, 4) uint8 array"));
    }
    let data: Vec<u8> = pixels.readonly().as_array().iter().copied().collect();
    write_png(path, shape[1] as u32, shape[0] as u32, &data).map_err(PyIOError::new_err)
}

#[pyfunction]
fn read_png<'py>(py: Python<'py>, path: &str) -> PyResult<Bound<'py, PyArray3<u8>>> {
    let file = File::open(path).map_err(|e| PyIOError::new_err(format!("{path}: {e}")))?;
    let mut dec = png::Decoder::new(std::io::BufReader::new(file));
    dec.set_transformations(png::Transformations::EXPAND);
    let mut reader = dec.read_info().map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
    let mut buf = vec![0u8; reader.output_buffer_size().ok_or_else(|| PyRuntimeError::new_err("image too large"))?];
    let info = reader.next_frame(&mut buf).map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
    let (w, h) = (info.width as usize, info.height as usize);
    let ch = info.color_type.samples();
    let mut rgba = vec![255u8; w * h * 4];
    for i in 0..w * h {
        let p = &buf[i * ch..i * ch + ch];
        let (r, g, b, a) = match ch {
            1 => (p[0], p[0], p[0], 255),
            2 => (p[0], p[0], p[0], p[1]),
            3 => (p[0], p[1], p[2], 255),
            _ => (p[0], p[1], p[2], p[3]),
        };
        rgba[i * 4..i * 4 + 4].copy_from_slice(&[r, g, b, a]);
    }
    numpy::PyArray1::from_vec(py, rgba).reshape([h, w, 4])
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(save_png, m)?)?;
    m.add_function(wrap_pyfunction!(read_png, m)?)?;
    Ok(())
}
