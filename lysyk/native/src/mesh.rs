use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use numpy::{AllowTypeChange, PyArray1, PyArray2, PyArrayLikeDyn, PyArrayMethods};
use pyo3::exceptions::{PyValueError};
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

fn make_mesh(vertices: Vec<[f32; 3]>, colors: Vec<[u8; 4]>, faces: Vec<[u32; 3]>) -> PyResult<Arc<MeshData>> {
    if vertices.is_empty() {
        return Err(PyValueError::new_err("mesh has no vertices"));
    }
    if colors.len() != vertices.len() {
        return Err(PyValueError::new_err("colors must have one entry per vertex"));
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
    let center = [(lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5, (lo[2] + hi[2]) * 0.5];
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
    let data = Arc::new(MeshData { vertices, colors, faces, gid, center, radius_c: rc.sqrt(), radius_o: ro.sqrt() as f32 });
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
        return Err(PyValueError::new_err(format!("{what}: length is not a multiple of 3")));
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
            return Err(PyValueError::new_err("colors: length is not a multiple of 4"));
        }
        let c: Vec<[u8; 4]> = c.chunks_exact(4).map(|x| [x[0], x[1], x[2], x[3]]).collect();
        let f: Vec<u32> = faces.as_array().iter().copied().collect();
        let f = chunks3(&f, "faces")?;
        Ok(Mesh { inner: make_mesh(v, c, f)? })
    }

    #[getter]
    fn gid(&self) -> u32 {
        self.inner.gid
    }

    #[getter]
    fn vertices<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray2<f32>> {
        let flat: Vec<f32> = self.inner.vertices.iter().flatten().copied().collect();
        PyArray1::from_vec(py, flat).reshape([self.inner.vertices.len(), 3]).unwrap()
    }

    #[getter]
    fn colors<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray2<u8>> {
        let flat: Vec<u8> = self.inner.colors.iter().flatten().copied().collect();
        PyArray1::from_vec(py, flat).reshape([self.inner.colors.len(), 4]).unwrap()
    }

    #[getter]
    fn faces<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray2<u32>> {
        let flat: Vec<u32> = self.inner.faces.iter().flatten().copied().collect();
        PyArray1::from_vec(py, flat).reshape([self.inner.faces.len(), 3]).unwrap()
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
        format!("Mesh(gid={}, vertices={}, triangles={})", self.inner.gid, self.inner.vertices.len(), self.inner.faces.len())
    }
}

type V3 = [f32; 3];

fn sub(a: V3, b: V3) -> V3 {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

fn cross(a: V3, b: V3) -> V3 {
    [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
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
        let mid = [(a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0, (a[2] + b[2] + c[2]) / 3.0];
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
    [0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
    [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
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
        _ => Err(PyValueError::new_err("color must be an RGB triple or an (N, 3) array")),
    }
}

fn v3(obj: &Bound<'_, PyAny>) -> PyResult<V3> {
    let a: [f64; 3] = obj.extract()?;
    Ok([a[0] as f32, a[1] as f32, a[2] as f32])
}

fn points(obj: &Bound<'_, PyAny>) -> PyResult<Vec<[f64; 3]>> {
    obj.extract()
}

#[pyclass(module = "lysyk.engine._native")]
pub struct MeshBuilder {
    v: Vec<V3>,
    c: Vec<[u8; 4]>,
    f: Vec<[u32; 3]>,
    tf: Option<(V3, f32)>,
}

impl MeshBuilder {
    pub fn empty() -> Self {
        MeshBuilder { v: Vec::new(), c: Vec::new(), f: Vec::new(), tf: None }
    }

    fn push(&mut self, mut v: Vec<V3>, f: Vec<[u32; 3]>, color: &Col, alpha: u8) -> PyResult<()> {
        if let Some((offset, yaw)) = self.tf {
            let (s, c) = (yaw as f64).sin_cos();
            let (c, s) = (c as f32, s as f32);
            for p in v.iter_mut() {
                let (x, z) = (p[0], p[2]);
                p[0] = c * x + s * z + offset[0];
                p[1] += offset[1];
                p[2] = -s * x + c * z + offset[2];
            }
        }
        let base = self.v.len() as u32;
        match color {
            Col::Uniform(u) => {
                let px = [to_u8(u[0]), to_u8(u[1]), to_u8(u[2]), alpha];
                self.c.extend(std::iter::repeat(px).take(v.len()));
            }
            Col::Each(list) => {
                if list.len() != v.len() {
                    return Err(PyValueError::new_err(format!("per-vertex colors: expected {} rows, got {}", v.len(), list.len())));
                }
                self.c.extend(list.iter().map(|u| [to_u8(u[0]), to_u8(u[1]), to_u8(u[2]), alpha]));
            }
        }
        self.v.extend(v);
        self.f.extend(f.into_iter().map(|t| [t[0] + base, t[1] + base, t[2] + base]));
        Ok(())
    }

    fn quads_impl(&mut self, q: &[[V3; 4]], colors: &Col, facing: &Facing, paint: f64) -> PyResult<()> {
        let n = q.len();
        if n == 0 {
            return Ok(());
        }
        let mut v = Vec::with_capacity(n * 4);
        for quad in q {
            v.extend_from_slice(quad);
        }
        let mut f = Vec::with_capacity(n * 2);
        for i in 0..n as u32 {
            let b = i * 4;
            f.push([b, b + 1, b + 2]);
            f.push([b, b + 2, b + 3]);
        }
        match facing {
            Facing::One(d) => orient_by_facing(&v, &mut f, |_| *d),
            Facing::Each(list) => {
                if list.len() != n {
                    return Err(PyValueError::new_err("facing must be a single vector or one per quad"));
                }
                orient_by_facing(&v, &mut f, |i| list[i / 2]);
            }
        }
        let col = match colors {
            Col::Uniform(u) => Col::Uniform(*u),
            Col::Each(list) => {
                if list.len() != n {
                    return Err(PyValueError::new_err("colors must be a single color or one per quad"));
                }
                Col::Each(list.iter().flat_map(|c| std::iter::repeat(*c).take(4)).collect())
            }
        };
        self.push(v, f, &col, paint_alpha(paint))
    }

    fn instances_impl(&mut self, mesh: &MeshData, pos: &[V3], scales: &[V3], tints: &[V3], yaws: Option<&[f32]>) {
        let t = pos.len();
        if t == 0 {
            return;
        }
        let nv = mesh.vertices.len();
        self.v.reserve(t * nv);
        self.c.reserve(t * nv);
        self.f.reserve(t * mesh.faces.len());
        let base0 = self.v.len() as u32;
        for i in 0..t {
            let sc = scales[i];
            let (cy, sy) = match yaws {
                Some(y) => (y[i].cos(), y[i].sin()),
                None => (1.0, 0.0),
            };
            for (vtx, col) in mesh.vertices.iter().zip(mesh.colors.iter()) {
                let mut p = [vtx[0] * sc[0], vtx[1] * sc[1], vtx[2] * sc[2]];
                if yaws.is_some() {
                    let (x, z) = (p[0], p[2]);
                    p[0] = cy * x + sy * z;
                    p[2] = -sy * x + cy * z;
                }
                self.v.push([p[0] + pos[i][0], p[1] + pos[i][1], p[2] + pos[i][2]]);
                let mut out = [col[0], col[1], col[2], 0];
                if col[3] > 0 {
                    for k in 0..3 {
                        out[k] = to_u8(col[k] as f32 * tints[i][k] / 255.0);
                    }
                }
                self.c.push(out);
            }
            let base = base0 + (i * nv) as u32;
            self.f.extend(mesh.faces.iter().map(|f| [f[0] + base, f[1] + base, f[2] + base]));
        }
    }

    pub fn finish(&self) -> PyResult<Mesh> {
        let mut f = self.f.clone();
        f.shrink_to_fit();
        Ok(Mesh { inner: make_mesh(self.v.clone(), self.c.clone(), f)? })
    }

    pub fn is_empty(&self) -> bool {
        self.v.is_empty()
    }
}

enum Facing {
    One(V3),
    Each(Vec<V3>),
}

fn parse_facing(obj: &Bound<'_, PyAny>) -> PyResult<Facing> {
    let a: PyArrayLikeDyn<'_, f32, AllowTypeChange> = obj.extract()?;
    let nd = a.as_array().ndim();
    let flat = flat_f32(&a);
    if nd == 1 && flat.len() == 3 {
        Ok(Facing::One([flat[0], flat[1], flat[2]]))
    } else if nd == 2 {
        Ok(Facing::Each(chunks3(&flat, "facing")?))
    } else {
        Err(PyValueError::new_err("facing must be a 3-vector or an (N, 3) array"))
    }
}

fn parse_quads(obj: &Bound<'_, PyAny>) -> PyResult<Vec<[V3; 4]>> {
    let a: PyArrayLikeDyn<'_, f32, AllowTypeChange> = obj.extract()?;
    let flat = flat_f32(&a);
    if flat.len() % 12 != 0 {
        return Err(PyValueError::new_err("quads must have shape (N, 4, 3)"));
    }
    Ok(flat
        .chunks_exact(12)
        .map(|c| [[c[0], c[1], c[2]], [c[3], c[4], c[5]], [c[6], c[7], c[8]], [c[9], c[10], c[11]]])
        .collect())
}

#[pymethods]
impl MeshBuilder {
    #[new]
    fn new() -> Self {
        Self::empty()
    }

    #[pyo3(signature = (offset, yaw=0.0))]
    fn begin_transform(&mut self, offset: &Bound<'_, PyAny>, yaw: f64) -> PyResult<()> {
        self.tf = Some((v3(offset)?, yaw as f32));
        Ok(())
    }

    fn end_transform(&mut self) {
        self.tf = None;
    }

    #[getter]
    fn vertex_count(&self) -> usize {
        self.v.len()
    }

    #[getter]
    fn triangle_count(&self) -> usize {
        self.f.len()
    }

    #[pyo3(signature = (bottom, top, color, paint=0.0))]
    fn hull(&mut self, bottom: &Bound<'_, PyAny>, top: &Bound<'_, PyAny>, color: &Bound<'_, PyAny>, paint: f64) -> PyResult<()> {
        let mut pts = points(bottom)?;
        pts.extend(points(top)?);
        if pts.len() != 8 {
            return Err(PyValueError::new_err("hull needs 4 bottom and 4 top points"));
        }
        let v: Vec<V3> = pts.iter().map(|p| [p[0] as f32, p[1] as f32, p[2] as f32]).collect();
        self.hull_raw(v, color, paint)
    }

    #[pyo3(signature = (base, bottom, top, height, color, paint=0.0, shift=0.0, shift_x=0.0))]
    fn prism(
        &mut self, base: &Bound<'_, PyAny>, bottom: (f64, f64), top: (f64, f64), height: f64,
        color: &Bound<'_, PyAny>, paint: f64, shift: f64, shift_x: f64,
    ) -> PyResult<()> {
        let [x, y, z]: [f64; 3] = base.extract()?;
        let ring = |cx: f64, cy: f64, cz: f64, w: f64, l: f64| -> [V3; 4] {
            let p = |a: f64, b: f64, c: f64| [a as f32, b as f32, c as f32];
            [
                p(cx - w / 2.0, cy, cz - l / 2.0), p(cx + w / 2.0, cy, cz - l / 2.0),
                p(cx + w / 2.0, cy, cz + l / 2.0), p(cx - w / 2.0, cy, cz + l / 2.0),
            ]
        };
        let mut v: Vec<V3> = ring(x, y, z, bottom.0, bottom.1).to_vec();
        v.extend(ring(x + shift_x, y + height, z + shift, top.0, top.1));
        self.hull_raw(v, color, paint)
    }

    #[pyo3(name = "box", signature = (center, size, color, paint=0.0))]
    fn box_(&mut self, center: &Bound<'_, PyAny>, size: &Bound<'_, PyAny>, color: &Bound<'_, PyAny>, paint: f64) -> PyResult<()> {
        let [cx, cy, cz]: [f64; 3] = center.extract()?;
        let [sx, sy, sz]: [f64; 3] = size.extract()?;
        let ring = |cy: f64| -> [V3; 4] {
            let p = |a: f64, b: f64, c: f64| [a as f32, b as f32, c as f32];
            [
                p(cx - sx / 2.0, cy, cz - sz / 2.0), p(cx + sx / 2.0, cy, cz - sz / 2.0),
                p(cx + sx / 2.0, cy, cz + sz / 2.0), p(cx - sx / 2.0, cy, cz + sz / 2.0),
            ]
        };
        let mut v: Vec<V3> = ring(cy - sy / 2.0).to_vec();
        v.extend(ring(cy - sy / 2.0 + sy));
        self.hull_raw(v, color, paint)
    }

    #[pyo3(signature = (center, radius, length, axis, color, paint=0.0, segments=12, radius_top=None))]
    fn cylinder(
        &mut self, center: &Bound<'_, PyAny>, radius: f64, length: f64, axis: &str, color: &Bound<'_, PyAny>,
        paint: f64, segments: usize, radius_top: Option<f64>,
    ) -> PyResult<()> {
        let seg = segments.max(3);
        let r1 = radius_top.unwrap_or(radius);
        let h = length / 2.0;
        let step = std::f64::consts::TAU / seg as f64;
        let mut v: Vec<V3> = Vec::with_capacity(seg * 2 + 2);
        for i in 0..seg {
            let a = i as f64 * step;
            v.push([(radius * a.cos()) as f32, (-h) as f32, (radius * a.sin()) as f32]);
        }
        for i in 0..seg {
            let a = i as f64 * step;
            v.push([(r1 * a.cos()) as f32, h as f32, (r1 * a.sin()) as f32]);
        }
        v.push([0.0, (-h) as f32, 0.0]);
        v.push([0.0, h as f32, 0.0]);
        let (cb, ct) = (2 * seg as u32, 2 * seg as u32 + 1);
        let s = seg as u32;
        let mut f = Vec::with_capacity(seg * 4);
        for i in 0..s {
            let j = (i + 1) % s;
            f.push([i, j, s + j]);
            f.push([i, s + j, s + i]);
            f.push([cb, j, i]);
            f.push([ct, s + i, s + j]);
        }
        match axis {
            "x" => v.iter_mut().for_each(|p| *p = [p[1], p[0], p[2]]),
            "z" => v.iter_mut().for_each(|p| *p = [p[0], p[2], p[1]]),
            _ => {}
        }
        let c = v3(center)?;
        v.iter_mut().for_each(|p| *p = [p[0] + c[0], p[1] + c[1], p[2] + c[2]]);
        orient_by_center(&v, &mut f, c);
        let col = parse_col(color)?;
        self.push(v, f, &col, paint_alpha(paint))
    }

    #[pyo3(signature = (center, radii, color, paint=0.0, rings=4, segments=8, inside=false, jitter=0.0, rng=None))]
    fn ellipsoid(
        &mut self, center: &Bound<'_, PyAny>, radii: &Bound<'_, PyAny>, color: &Bound<'_, PyAny>, paint: f64,
        rings: usize, segments: usize, inside: bool, jitter: f64, rng: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let r: [f64; 3] = radii.extract()?;
        let mut v: Vec<V3> = vec![[0.0, r[1] as f32, 0.0]];
        for ring in 1..rings {
            let phi = std::f64::consts::PI * ring as f64 / rings as f64;
            for s in 0..segments {
                let th = std::f64::consts::TAU * s as f64 / segments as f64;
                v.push([
                    (r[0] * phi.sin() * th.cos()) as f32,
                    (r[1] * phi.cos()) as f32,
                    (r[2] * phi.sin() * th.sin()) as f32,
                ]);
            }
        }
        v.push([0.0, (-r[1]) as f32, 0.0]);
        if jitter > 0.0 {
            if let Some(rng) = rng {
                let n = v.len();
                let rnd: PyArrayLikeDyn<'_, f64, AllowTypeChange> = rng.call_method1("random", ((n, 1usize),))?.extract()?;
                let rnd: Vec<f64> = rnd.as_array().iter().copied().collect();
                for (p, u) in v.iter_mut().zip(rnd.iter()) {
                    let k = (1.0 + jitter * (u - 0.5)) as f32;
                    p[0] *= k;
                    p[1] *= k;
                    p[2] *= k;
                }
            }
        }
        let (segs, rgs) = (segments as u32, rings as u32);
        let mut f: Vec<[u32; 3]> = Vec::new();
        for s in 0..segs {
            f.push([0, 1 + s, 1 + (s + 1) % segs]);
        }
        for ring in 0..rgs.saturating_sub(2) {
            let a = 1 + ring * segs;
            let b = a + segs;
            for s in 0..segs {
                let t = (s + 1) % segs;
                f.push([a + s, b + s, b + t]);
                f.push([a + s, b + t, a + t]);
            }
        }
        let last = v.len() as u32 - 1;
        let a = 1 + rgs.saturating_sub(2) * segs;
        for s in 0..segs {
            f.push([last, a + (s + 1) % segs, a + s]);
        }
        let c = v3(center)?;
        v.iter_mut().for_each(|p| *p = [p[0] + c[0], p[1] + c[1], p[2] + c[2]]);
        orient_by_center(&v, &mut f, c);
        if inside {
            f.iter_mut().for_each(|t| t.swap(1, 2));
        }
        let col = parse_col(color)?;
        self.push(v, f, &col, paint_alpha(paint))
    }

    #[pyo3(signature = (q, colors, facing, paint=0.0))]
    fn quads(&mut self, q: &Bound<'_, PyAny>, colors: &Bound<'_, PyAny>, facing: &Bound<'_, PyAny>, paint: f64) -> PyResult<()> {
        let q = parse_quads(q)?;
        let col = parse_col(colors)?;
        let fac = parse_facing(facing)?;
        self.quads_impl(&q, &col, &fac, paint)
    }

    #[pyo3(signature = (mesh, offset=None, yaw=0.0, scale=1.0, tint=None))]
    fn add_mesh(
        &mut self, mesh: &Mesh, offset: Option<&Bound<'_, PyAny>>, yaw: f64, scale: f64, tint: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let m = &mesh.inner;
        let off = match offset {
            Some(o) => v3(o)?,
            None => [0.0; 3],
        };
        let scale = scale as f32;
        let (c, s) = ((yaw.cos()) as f32, (yaw.sin()) as f32);
        let tint = match tint {
            Some(t) if !t.is_none() => Some(v3(t)?),
            _ => None,
        };
        let base = self.v.len() as u32;
        for (p, col) in m.vertices.iter().zip(m.colors.iter()) {
            let mut x = p[0] * scale;
            let y = p[1] * scale;
            let mut z = p[2] * scale;
            if yaw != 0.0 {
                let (ox, oz) = (x, z);
                x = c * ox + s * oz;
                z = -s * ox + c * oz;
            }
            self.v.push([x + off[0], y + off[1], z + off[2]]);
            let mut out = [col[0], col[1], col[2], col[3]];
            if let Some(t) = tint {
                if col[3] > 0 {
                    for k in 0..3 {
                        out[k] = to_u8(col[k] as f32 * (t[k] / 255.0));
                    }
                }
                out[3] = 0;
            }
            self.c.push(out);
        }
        self.f.extend(m.faces.iter().map(|f| [f[0] + base, f[1] + base, f[2] + base]));
        Ok(())
    }

    fn heightfield(
        &mut self, xs: PyArrayLikeDyn<'_, f32, AllowTypeChange>, zs: PyArrayLikeDyn<'_, f32, AllowTypeChange>,
        heights: PyArrayLikeDyn<'_, f32, AllowTypeChange>, colors: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let xs = flat_f32(&xs);
        let zs = flat_f32(&zs);
        let hs = flat_f32(&heights);
        let (nx, nz) = (xs.len(), zs.len());
        if nx < 2 || nz < 2 || hs.len() != nx * nz {
            return Err(PyValueError::new_err("heightfield: heights must have shape (len(xs), len(zs))"));
        }
        let mut v = Vec::with_capacity(nx * nz);
        for ix in 0..nx {
            for iz in 0..nz {
                v.push([xs[ix], hs[ix * nz + iz], zs[iz]]);
            }
        }
        let mut f = Vec::with_capacity((nx - 1) * (nz - 1) * 2);
        let (mut t1, mut t2) = (Vec::new(), Vec::new());
        for ix in 0..nx - 1 {
            for iz in 0..nz - 1 {
                let a = (ix * nz + iz) as u32;
                let b = ((ix + 1) * nz + iz) as u32;
                let c = ((ix + 1) * nz + iz + 1) as u32;
                let d = (ix * nz + iz + 1) as u32;
                if (ix + iz) % 2 == 0 {
                    t1.push([a, b, c]);
                    t2.push([a, c, d]);
                } else {
                    t1.push([a, b, d]);
                    t2.push([b, c, d]);
                }
            }
        }
        f.extend(t1);
        f.extend(t2);
        orient_by_facing(&v, &mut f, |_| [0.0, 1.0, 0.0]);
        let col = parse_col(colors)?;
        self.push(v, f, &col, 0)
    }

    #[pyo3(signature = (mesh, positions, scales, tints, yaws=None))]
    fn add_instances(
        &mut self, mesh: &Mesh, positions: PyArrayLikeDyn<'_, f32, AllowTypeChange>, scales: PyArrayLikeDyn<'_, f32, AllowTypeChange>,
        tints: PyArrayLikeDyn<'_, f32, AllowTypeChange>, yaws: Option<PyArrayLikeDyn<'_, f32, AllowTypeChange>>,
    ) -> PyResult<()> {
        let pos = chunks3(&flat_f32(&positions), "positions")?;
        let t = pos.len();
        let sflat = flat_f32(&scales);
        let sc: Vec<V3> = if scales.as_array().ndim() == 1 {
            if sflat.len() != t {
                return Err(PyValueError::new_err("scales: expected one value per instance"));
            }
            sflat.iter().map(|s| [*s, *s, *s]).collect()
        } else {
            chunks3(&sflat, "scales")?
        };
        let ti = chunks3(&flat_f32(&tints), "tints")?;
        if sc.len() != t || ti.len() != t {
            return Err(PyValueError::new_err("scales and tints must match positions"));
        }
        let ys = yaws.map(|y| flat_f32(&y));
        if let Some(y) = &ys {
            if y.len() != t {
                return Err(PyValueError::new_err("yaws: expected one value per instance"));
            }
        }
        self.instances_impl(&mesh.inner, &pos, &sc, &ti, ys.as_deref());
        Ok(())
    }

    fn build(&self) -> PyResult<Mesh> {
        self.finish()
    }
}

impl MeshBuilder {
    fn hull_raw(&mut self, v: Vec<V3>, color: &Bound<'_, PyAny>, paint: f64) -> PyResult<()> {
        let mut mean = [0.0f32; 3];
        for p in &v {
            for k in 0..3 {
                mean[k] += p[k];
            }
        }
        let n = v.len() as f32;
        let center = [mean[0] / n, mean[1] / n, mean[2] / n];
        let mut f = BOX_FACES.to_vec();
        orient_by_center(&v, &mut f, center);
        let col = parse_col(color)?;
        self.push(v, f, &col, paint_alpha(paint))
    }
}

#[pyclass(module = "lysyk.engine._native")]
pub struct TiledBuilder {
    tile: f64,
    order: Vec<(i64, i64, bool)>,
    cells: HashMap<(i64, i64, bool), Py<MeshBuilder>>,
}

impl TiledBuilder {
    fn cell(&mut self, py: Python<'_>, tx: i64, tz: i64, glow: bool) -> PyResult<Py<MeshBuilder>> {
        let key = (tx, tz, glow);
        if let Some(b) = self.cells.get(&key) {
            return Ok(b.clone_ref(py));
        }
        let b = Py::new(py, MeshBuilder::empty())?;
        self.cells.insert(key, b.clone_ref(py));
        self.order.push(key);
        Ok(b)
    }

    fn key_of(&self, x: f64, z: f64) -> (i64, i64) {
        ((x / self.tile).floor() as i64, (z / self.tile).floor() as i64)
    }

    fn groups(&self, centers: &[[f32; 2]]) -> Vec<Vec<usize>> {
        let t = self.tile as f32;
        let mut by_code: std::collections::BTreeMap<i64, Vec<usize>> = std::collections::BTreeMap::new();
        for (i, c) in centers.iter().enumerate() {
            let tx = (c[0] / t).floor() as i64;
            let tz = (c[1] / t).floor() as i64;
            by_code.entry(tx.wrapping_mul(100003).wrapping_add(tz)).or_default().push(i);
        }
        by_code.into_values().collect()
    }
}

#[pymethods]
impl TiledBuilder {
    #[new]
    #[pyo3(signature = (tile=256.0))]
    fn new(tile: f64) -> Self {
        TiledBuilder { tile, order: Vec::new(), cells: HashMap::new() }
    }

    #[getter]
    fn tile(&self) -> f64 {
        self.tile
    }

    #[pyo3(signature = (x, z, glow=false))]
    fn at(&mut self, py: Python<'_>, x: f64, z: f64, glow: bool) -> PyResult<Py<MeshBuilder>> {
        let (tx, tz) = self.key_of(x, z);
        self.cell(py, tx, tz, glow)
    }

    #[pyo3(signature = (q, colors, facing, paint=0.0, glow=false))]
    fn quads(
        &mut self, py: Python<'_>, q: &Bound<'_, PyAny>, colors: &Bound<'_, PyAny>, facing: &Bound<'_, PyAny>, paint: f64, glow: bool,
    ) -> PyResult<()> {
        let q = parse_quads(q)?;
        if q.is_empty() {
            return Ok(());
        }
        let col = parse_col(colors)?;
        let fac = parse_facing(facing)?;
        let centers: Vec<[f32; 2]> = q
            .iter()
            .map(|quad| {
                let sx = ((quad[0][0] + quad[1][0]) + quad[2][0]) + quad[3][0];
                let sz = ((quad[0][2] + quad[1][2]) + quad[2][2]) + quad[3][2];
                [sx / 4.0, sz / 4.0]
            })
            .collect();
        for sel in self.groups(&centers) {
            let first = centers[sel[0]];
            let (tx, tz) = self.key_of(first[0] as f64, first[1] as f64);
            let cell = self.cell(py, tx, tz, glow)?;
            let sub_q: Vec<[V3; 4]> = sel.iter().map(|&i| q[i]).collect();
            let sub_c = match &col {
                Col::Each(l) if l.len() == q.len() => Col::Each(sel.iter().map(|&i| l[i]).collect()),
                Col::Each(l) => Col::Each(l.clone()),
                Col::Uniform(u) => Col::Uniform(*u),
            };
            let sub_f = match &fac {
                Facing::Each(l) if l.len() == q.len() => Facing::Each(sel.iter().map(|&i| l[i]).collect()),
                Facing::Each(l) => Facing::Each(l.clone()),
                Facing::One(d) => Facing::One(*d),
            };
            cell.bind(py).borrow_mut().quads_impl(&sub_q, &sub_c, &sub_f, paint)?;
        }
        Ok(())
    }

    #[pyo3(signature = (mesh, positions, scales, tints, yaws=None, glow=false))]
    fn instances(
        &mut self, py: Python<'_>, mesh: &Mesh, positions: PyArrayLikeDyn<'_, f32, AllowTypeChange>, scales: PyArrayLikeDyn<'_, f32, AllowTypeChange>,
        tints: PyArrayLikeDyn<'_, f32, AllowTypeChange>, yaws: Option<PyArrayLikeDyn<'_, f32, AllowTypeChange>>, glow: bool,
    ) -> PyResult<()> {
        let pos = chunks3(&flat_f32(&positions), "positions")?;
        if pos.is_empty() {
            return Ok(());
        }
        let t = pos.len();
        let sflat = flat_f32(&scales);
        let sc: Vec<V3> = if scales.as_array().ndim() == 1 {
            sflat.iter().map(|s| [*s, *s, *s]).collect()
        } else {
            chunks3(&sflat, "scales")?
        };
        let ti = chunks3(&flat_f32(&tints), "tints")?;
        let ys = yaws.map(|y| flat_f32(&y));
        if sc.len() != t || ti.len() != t || ys.as_ref().map_or(false, |y| y.len() != t) {
            return Err(PyValueError::new_err("instances: positions, scales, tints and yaws must have the same length"));
        }
        let centers: Vec<[f32; 2]> = pos.iter().map(|p| [p[0], p[2]]).collect();
        for sel in self.groups(&centers) {
            let first = centers[sel[0]];
            let (tx, tz) = self.key_of(first[0] as f64, first[1] as f64);
            let cell = self.cell(py, tx, tz, glow)?;
            let p: Vec<V3> = sel.iter().map(|&i| pos[i]).collect();
            let s: Vec<V3> = sel.iter().map(|&i| sc[i]).collect();
            let tn: Vec<V3> = sel.iter().map(|&i| ti[i]).collect();
            let y: Option<Vec<f32>> = ys.as_ref().map(|y| sel.iter().map(|&i| y[i]).collect());
            cell.bind(py).borrow_mut().instances_impl(&mesh.inner, &p, &s, &tn, y.as_deref());
        }
        Ok(())
    }

    fn build<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        for key in &self.order {
            let b = self.cells[key].bind(py).borrow();
            if !b.is_empty() {
                let mesh = Py::new(py, b.finish()?)?;
                out.append(((key.0, key.1), key.2, mesh))?;
            }
        }
        Ok(out)
    }
}

#[pyfunction]
pub fn mesh_registry_stats() -> (usize, usize, usize) {
    registry_stats()
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Mesh>()?;
    m.add_class::<MeshBuilder>()?;
    m.add_class::<TiledBuilder>()?;
    m.add("VERTEX_STRIDE", VERTEX_STRIDE)?;
    m.add_function(wrap_pyfunction!(mesh_registry_stats, m)?)?;
    Ok(())
}
