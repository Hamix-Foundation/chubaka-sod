use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::sync::Mutex;

use pyo3::exceptions::{PyIOError, PyIndexError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use zune_core::colorspace::ColorSpace;
use zune_core::options::DecoderOptions;
use zune_jpeg::JpegDecoder;

use crate::canvas::Texture;

const MAGIC: &[u8; 4] = b"LYV1";
const HEADER: usize = 24;
const ENTRY: usize = 16;

struct Entry {
    offset: u64,
    size: u32,
    pts: f64,
}

#[pyclass(module = "lysyk.engine._native")]
pub struct VideoStream {
    file: Mutex<File>,
    index: Vec<Entry>,
    width: u32,
    height: u32,
    fps: f32,
    duration: f64,
    path: String,
}

fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]])
}

fn u64_at(b: &[u8], o: usize) -> u64 {
    let mut a = [0u8; 8];
    a.copy_from_slice(&b[o..o + 8]);
    u64::from_le_bytes(a)
}

impl VideoStream {
    fn read_frame(&self, i: usize) -> PyResult<Vec<u8>> {
        let e = self.index.get(i).ok_or_else(|| PyIndexError::new_err("frame index out of range"))?;
        let mut buf = vec![0u8; e.size as usize];
        let mut f = self.file.lock().unwrap();
        f.seek(SeekFrom::Start(e.offset)).map_err(|x| PyIOError::new_err(x.to_string()))?;
        f.read_exact(&mut buf).map_err(|x| PyIOError::new_err(x.to_string()))?;
        Ok(buf)
    }

    fn decode_rgba(&self, i: usize) -> PyResult<Vec<u8>> {
        let data = self.read_frame(i)?;
        let options = DecoderOptions::default().jpeg_set_out_colorspace(ColorSpace::RGBA);
        let mut dec = JpegDecoder::new_with_options(&data[..], options);
        dec.decode_headers().map_err(|e| PyRuntimeError::new_err(format!("{}: frame {i}: {e:?}", self.path)))?;
        let info = dec.info().ok_or_else(|| PyRuntimeError::new_err("missing frame info"))?;
        if info.width as u32 != self.width || info.height as u32 != self.height {
            return Err(PyRuntimeError::new_err(format!("{}: frame {i} has size {}x{}, expected {}x{}", self.path, info.width, info.height, self.width, self.height)));
        }
        let size = dec.output_buffer_size().ok_or_else(|| PyRuntimeError::new_err("cannot size frame buffer"))?;
        let mut out = vec![0u8; size];
        dec.decode_into(&mut out).map_err(|e| PyRuntimeError::new_err(format!("{}: frame {i}: {e:?}", self.path)))?;
        Ok(out)
    }
}

#[pymethods]
impl VideoStream {
    #[new]
    fn new(path: &str) -> PyResult<Self> {
        let mut file = File::open(path).map_err(|e| PyIOError::new_err(format!("{path}: {e}")))?;
        let mut head = [0u8; HEADER];
        file.read_exact(&mut head).map_err(|e| PyIOError::new_err(format!("{path}: {e}")))?;
        if &head[0..4] != MAGIC {
            return Err(PyValueError::new_err(format!("{path}: not a Lysyk video (.lyv) file")));
        }
        let width = u32_at(&head, 4);
        let height = u32_at(&head, 8);
        let count = u32_at(&head, 12) as usize;
        let fps = f32::from_le_bytes([head[16], head[17], head[18], head[19]]);
        if width == 0 || height == 0 || count == 0 {
            return Err(PyValueError::new_err(format!("{path}: empty video")));
        }
        let mut table = vec![0u8; count * ENTRY];
        file.read_exact(&mut table).map_err(|e| PyIOError::new_err(format!("{path}: {e}")))?;
        let mut index = Vec::with_capacity(count);
        for k in 0..count {
            let o = k * ENTRY;
            index.push(Entry { offset: u64_at(&table, o), size: u32_at(&table, o + 8), pts: u32_at(&table, o + 12) as f64 / 1000.0 });
        }
        let tail = if fps > 0.0 { 1.0 / fps as f64 } else { 0.04 };
        let duration = index.last().map_or(0.0, |e| e.pts) + tail;
        Ok(VideoStream { file: Mutex::new(file), index, width, height, fps, duration, path: path.to_string() })
    }

    #[getter]
    fn width(&self) -> u32 {
        self.width
    }

    #[getter]
    fn height(&self) -> u32 {
        self.height
    }

    #[getter]
    fn fps(&self) -> f32 {
        self.fps
    }

    #[getter]
    fn frame_count(&self) -> usize {
        self.index.len()
    }

    #[getter]
    fn duration(&self) -> f64 {
        self.duration
    }

    fn frame_index(&self, t: f64) -> usize {
        let n = self.index.partition_point(|e| e.pts <= t);
        n.saturating_sub(1)
    }

    fn frame_time(&self, i: usize) -> PyResult<f64> {
        self.index.get(i).map(|e| e.pts).ok_or_else(|| PyIndexError::new_err("frame index out of range"))
    }

    fn decode<'py>(&self, py: Python<'py>, i: usize) -> PyResult<Bound<'py, PyBytes>> {
        let pixels = py.detach(|| self.decode_rgba(i))?;
        Ok(PyBytes::new(py, &pixels))
    }

    fn upload(&self, py: Python<'_>, texture: &Bound<'_, Texture>, i: usize) -> PyResult<()> {
        let tex = texture.borrow().inner.clone();
        if tex.width() != self.width || tex.height() != self.height {
            return Err(PyValueError::new_err("texture size does not match the video"));
        }
        let pixels = py.detach(|| self.decode_rgba(i))?;
        tex.write_rgba(0, 0, self.width, self.height, &pixels);
        Ok(())
    }

    fn __repr__(&self) -> String {
        format!("VideoStream({}x{}, {} frames, {:.2}s)", self.width, self.height, self.index.len(), self.duration)
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<VideoStream>()
}
