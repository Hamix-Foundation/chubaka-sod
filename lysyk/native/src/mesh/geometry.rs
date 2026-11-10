use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use numpy::{AllowTypeChange, PyArray1, PyArray2, PyArrayLikeDyn, PyArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyList;

pub const VERTEX_STRIDE: usize = 16;

pub struct MeshData {
    pub vertices: Vec<[f32; 3]>,
    pub colors: Vec<[u8; 4]>,
    pub faces: Vec<[u32; 3]>,
    pub gid: u32,
    pub center: [f32; 3],
    pub radius_c: f32,
    pub radius_o: f32,
}

static REGISTRY: RwLock<Vec<Arc<MeshData>>> = RwLock::new(Vec::new());

pub fn mesh_by_gid(gid: u32) -> Option<Arc<MeshData>> {
    REGISTRY.read().unwrap().get(gid as usize).cloned()
}

pub fn registry_stats() -> (usize, usize, usize) {
    let r = REGISTRY.read().unwrap();
    let mut v = 0;
    let mut t = 0;
    for m in r.iter() {
        v += m.vertices.len();
        t += m.faces.len();
    }
    (r.len(), v, t)
}

fn make_mesh(
    vertices: Vec<[f32; 3]>,
    colors: Vec<[u8; 4]>,
    faces: Vec<[u32; 3]>,
) -> PyResult<Arc<MeshData>> {
    if vertices.is_empty() {
        return Err(PyValueError::new_err("mesh has no vertices"));
    }
    if colors.len() != vertices.len() {
        return Err(PyValueError::new_err(
            "colors must have one entry per vertex",
        ));
    }
    let nv = vertices.len() as u32;
    if faces.iter().any(|f| f[0] >= nv || f[1] >= nv || f[2] >= nv) {
        return Err(PyValueError::new_err("face index out of range"));
    }
    let mut lo = [f32::INFINITY; 3];
    let mut hi = [f32::NEG_INFINITY; 3];
    for v in &vertices {
        for k in 0..3 {
            lo[k] = lo[k].min(v[k]);
            hi[k] = hi[k].max(v[k]);
        }
    }
    let center = [
        (lo[0] + hi[0]) * 0.5,
        (lo[1] + hi[1]) * 0.5,
        (lo[2] + hi[2]) * 0.5,
    ];
    let mut rc = 0.0f32;
    let mut ro = 0.0f64;
    for v in &vertices {
        let d = [v[0] - center[0], v[1] - center[1], v[2] - center[2]];
        rc = rc.max(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
        let o = (v[0] as f64).powi(2) + (v[1] as f64).powi(2) + (v[2] as f64).powi(2);
        ro = ro.max(o);
    }
    let mut reg = REGISTRY.write().unwrap();
    let gid = reg.len() as u32;
    let data = Arc::new(MeshData {
        vertices,
        colors,
        faces,
        gid,
        center,
        radius_c: rc.sqrt(),
        radius_o: ro.sqrt() as f32,
    });
    reg.push(data.clone());
    Ok(data)
}

#[pyclass(module = "lysyk.engine._native")]
pub struct Mesh {
    pub inner: Arc<MeshData>,
}

fn flat_f32(a: &PyArrayLikeDyn<'_, f32, AllowTypeChange>) -> Vec<f32> {
    a.as_array().iter().copied().collect()
}

fn chunks3<T: Copy>(v: &[T], what: &str) -> PyResult<Vec<[T; 3]>> {
    if v.len() % 3 != 0 {
        return Err(PyValueError::new_err(format!(
            "{what}: length is not a multiple of 3"
        )));
    }
    Ok(v.chunks_exact(3).map(|c| [c[0], c[1], c[2]]).collect())
}

#[pymethods]
impl Mesh {
    #[new]
    fn new(
        vertices: PyArrayLikeDyn<'_, f32, AllowTypeChange>,
        colors: PyArrayLikeDyn<'_, u8, AllowTypeChange>,
        faces: PyArrayLikeDyn<'_, u32, AllowTypeChange>,
    ) -> PyResult<Self> {
        let v = chunks3(&flat_f32(&vertices), "vertices")?;
        let c: Vec<u8> = colors.as_array().iter().copied().collect();
        if c.len() % 4 != 0 {
            return Err(PyValueError::new_err(
                "colors: length is not a multiple of 4",
            ));
        }
        let c: Vec<[u8; 4]> = c
            .chunks_exact(4)
            .map(|x| [x[0], x[1], x[2], x[3]])
            .collect();
        let f: Vec<u32> = faces.as_array().iter().copied().collect();
        let f = chunks3(&f, "faces")?;
        Ok(Mesh {
            inner: make_mesh(v, c, f)?,
        })
    }

    #[getter]
    fn gid(&self) -> u32 {
        self.inner.gid
    }

    #[getter]
    fn vertices<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray2<f32>> {
        let flat: Vec<f32> = self.inner.vertices.iter().flatten().copied().collect();
        PyArray1::from_vec(py, flat)
            .reshape([self.inner.vertices.len(), 3])
            .unwrap()
    }

    #[getter]
    fn colors<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray2<u8>> {
        let flat: Vec<u8> = self.inner.colors.iter().flatten().copied().collect();
        PyArray1::from_vec(py, flat)
            .reshape([self.inner.colors.len(), 4])
            .unwrap()
    }

    #[getter]
    fn faces<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray2<u32>> {
        let flat: Vec<u32> = self.inner.faces.iter().flatten().copied().collect();
        PyArray1::from_vec(py, flat)
            .reshape([self.inner.faces.len(), 3])
            .unwrap()
    }

    #[getter]
    fn center<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray1<f32>> {
        PyArray1::from_slice(py, &self.inner.center)
    }

    #[getter]
    fn radius_c(&self) -> f32 {
        self.inner.radius_c
    }

    #[getter]
    fn radius_o(&self) -> f32 {
        self.inner.radius_o
    }

    #[getter]
    fn vertex_count(&self) -> usize {
        self.inner.vertices.len()
    }

    #[getter]
    fn triangle_count(&self) -> usize {
        self.inner.faces.len()
    }

    fn __repr__(&self) -> String {
        format!(
            "Mesh(gid={}, vertices={}, triangles={})",
            self.inner.gid,
            self.inner.vertices.len(),
            self.inner.faces.len()
        )
    }
}

type V3 = [f32; 3];

fn sub(a: V3, b: V3) -> V3 {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

fn cross(a: V3, b: V3) -> V3 {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn dot(a: V3, b: V3) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

fn orient_by_center(v: &[V3], f: &mut [[u32; 3]], center: V3) {
    for t in f.iter_mut() {
        let a = v[t[0] as usize];
        let b = v[t[1] as usize];
        let c = v[t[2] as usize];
        let n = cross(sub(b, a), sub(c, a));
        let mid = [
            (a[0] + b[0] + c[0]) / 3.0,
            (a[1] + b[1] + c[1]) / 3.0,
            (a[2] + b[2] + c[2]) / 3.0,
        ];
        if dot(n, sub(mid, center)) < 0.0 {
            t.swap(1, 2);
        }
    }
}

fn orient_by_facing(v: &[V3], f: &mut [[u32; 3]], facing: impl Fn(usize) -> V3) {
    for (i, t) in f.iter_mut().enumerate() {
        let a = v[t[0] as usize];
        let b = v[t[1] as usize];
        let c = v[t[2] as usize];
        let n = cross(sub(b, a), sub(c, a));
        if dot(n, facing(i)) < 0.0 {
            t.swap(1, 2);
        }
    }
}

const BOX_FACES: [[u32; 3]; 12] = [
    [0, 1, 2],
    [0, 2, 3],
    [4, 5, 6],
    [4, 6, 7],
    [0, 1, 5],
    [0, 5, 4],
    [1, 2, 6],
    [1, 6, 5],
    [2, 3, 7],
    [2, 7, 6],
    [3, 0, 4],
    [3, 4, 7],
];

enum Col {
    Uniform([f32; 3]),
    Each(Vec<[f32; 3]>),
}

fn to_u8(x: f32) -> u8 {
    x.clamp(0.0, 255.0) as u8
}

fn paint_alpha(paint: f64) -> u8 {
    (paint * 255.0).round_ties_even().clamp(0.0, 255.0) as u8
}

fn parse_col(obj: &Bound<'_, PyAny>) -> PyResult<Col> {
    let a: PyArrayLikeDyn<'_, f32, AllowTypeChange> = obj.extract()?;
    let nd = a.as_array().ndim();
    let flat = flat_f32(&a);
    match nd {
        1 if flat.len() >= 3 => Ok(Col::Uniform([flat[0], flat[1], flat[2]])),
        n if n >= 2 => Ok(Col::Each(chunks3(&flat, "color")?)),
        _ => Err(PyValueError::new_err(
            "color must be an RGB triple or an (N, 3) array",
        )),
    }
}

fn v3(obj: &Bound<'_, PyAny>) -> PyResult<V3> {
    let a: [f64; 3] = obj.extract()?;
    Ok([a[0] as f32, a[1] as f32, a[2] as f32])
}

fn points(obj: &Bound<'_, PyAny>) -> PyResult<Vec<[f64; 3]>> {
    obj.extract()
}
