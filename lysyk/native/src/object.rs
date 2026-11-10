use numpy::{AllowTypeChange, PyArray1, PyArray2, PyArrayLike2, PyArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::mesh::Mesh;
use crate::store::{self, store, COL_COLOR, COL_MODE, COL_VISIBLE};

pub const MODE_LIT: i32 = 0;
pub const MODE_GLOW: i32 = 1;
pub const MODE_SKY: i32 = 2;
pub const MODE_CLOUD: i32 = 3;
pub const MODE_WATER: i32 = 4;

#[pyclass(subclass, dict, weakref, module = "lysyk.engine._native")]
pub struct GameObject {
    #[pyo3(get)]
    pub slot: u32,
    mesh: Option<Py<Mesh>>,
}

impl Drop for GameObject {
    fn drop(&mut self) {
        store().release(self.slot);
    }
}

fn set3(slot: u32, from: usize, v: [f64; 3]) {
    let r = store().row(slot);
    r[from] = v[0] as f32;
    r[from + 1] = v[1] as f32;
    r[from + 2] = v[2] as f32;
}

fn pack_rgb(c: [f64; 3]) -> u32 {
    (c[0] as i64 as u32 & 255)
        | ((c[1] as i64 as u32 & 255) << 8)
        | ((c[2] as i64 as u32 & 255) << 16)
}

#[pymethods]
impl GameObject {
    #[new]
    #[pyo3(signature = (mesh, color=None, position=None, rotation=None, scale=None, mode=MODE_LIT, cast=false, gloss=0.0))]
    pub fn new(
        py: Python<'_>,
        mesh: Option<Py<Mesh>>,
        color: Option<[f64; 3]>,
        position: Option<[f64; 3]>,
        rotation: Option<[f64; 3]>,
        scale: Option<[f64; 3]>,
        mode: i32,
        cast: bool,
        gloss: f64,
    ) -> PyResult<Self> {
        let slot = store().alloc()?;
        let s = store();
        s.set_mesh_id(
            slot,
            mesh.as_ref()
                .map_or(-1, |m| m.bind(py).borrow().inner.gid as i32),
        );
        s.set_cast(slot, cast);
        s.row(slot)[COL_MODE] = mode as f32;
        let c = color.unwrap_or([255.0, 255.0, 255.0]);
        s.row_bits(slot)[COL_COLOR] = pack_rgb(c);
        if gloss != 0.0 {
            let bits = s.row_bits(slot);
            bits[COL_COLOR] = (bits[COL_COLOR] & 0x00FF_FFFF)
                | (((gloss.clamp(0.0, 1.0) * 255.0).round_ties_even() as u32) << 24);
        }
        if let Some(p) = position {
            set3(slot, 0, p);
        }
        if let Some(r) = rotation {
            set3(slot, 4, r);
        }
        if let Some(sc) = scale {
            set3(slot, 8, sc);
        }
        Ok(GameObject { slot, mesh })
    }

    #[getter]
    pub fn mesh(&self, py: Python<'_>) -> Option<Py<Mesh>> {
        self.mesh.as_ref().map(|m| m.clone_ref(py))
    }

    #[setter]
    fn set_mesh(&mut self, py: Python<'_>, mesh: Option<Py<Mesh>>) {
        store().set_mesh_id(
            self.slot,
            mesh.as_ref()
                .map_or(-1, |m| m.bind(py).borrow().inner.gid as i32),
        );
        self.mesh = mesh;
    }

    #[getter]
    fn cast(&self) -> bool {
        store().cast(self.slot)
    }

    #[setter]
    fn set_cast(&self, v: bool) {
        store().set_cast(self.slot, v);
    }

    #[getter]
    fn position<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray1<f32>>> {
        store::row_view(py, self.slot, 0, 3)
    }

    #[setter]
    fn set_position(&self, v: [f64; 3]) {
        set3(self.slot, 0, v);
    }

    #[getter]
    fn rotation<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray1<f32>>> {
        store::row_view(py, self.slot, 4, 7)
    }

    #[setter]
    fn set_rotation(&self, v: [f64; 3]) {
        set3(self.slot, 4, v);
    }

    #[getter]
    fn scale<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray1<f32>>> {
        store::row_view(py, self.slot, 8, 11)
    }

    #[setter]
    fn set_scale(&self, v: [f64; 3]) {
        set3(self.slot, 8, v);
    }

    #[getter]
    fn visible(&self) -> bool {
        store().row(self.slot)[COL_VISIBLE] > 0.5
    }

    #[setter]
    pub fn set_visible(&self, v: bool) {
        store().row(self.slot)[COL_VISIBLE] = if v { 1.0 } else { 0.0 };
    }

    #[getter]
    fn mode(&self) -> i32 {
        store().row(self.slot)[COL_MODE] as i32
    }

    #[setter]
    fn set_mode(&self, v: i32) {
        store().row(self.slot)[COL_MODE] = v as f32;
    }

    #[getter]
    fn gloss(&self) -> f64 {
        ((store().row_bits(self.slot)[COL_COLOR] >> 24) & 255) as f64 / 255.0
    }

    #[setter]
    fn set_gloss(&self, g: f64) {
        let bits = store().row_bits(self.slot);
        bits[COL_COLOR] = (bits[COL_COLOR] & 0x00FF_FFFF)
            | (((g.clamp(0.0, 1.0) * 255.0).round_ties_even() as u32) << 24);
    }

    #[getter]
    fn color(&self) -> (u32, u32, u32) {
        let c = store().row_bits(self.slot)[COL_COLOR];
        (c & 255, (c >> 8) & 255, (c >> 16) & 255)
    }

    #[setter]
    fn set_color(&self, v: [f64; 3]) {
        let bits = store().row_bits(self.slot);
        bits[COL_COLOR] = (bits[COL_COLOR] & 0xFF00_0000) | pack_rgb(v);
    }

    #[pyo3(signature = (x, y, z, rx=0.0, ry=0.0))]
    fn place(&self, x: f64, y: f64, z: f64, rx: f64, ry: f64) {
        let d = store().row(self.slot);
        d[0] = x as f32;
        d[1] = y as f32;
        d[2] = z as f32;
        d[4] = rx as f32;
        d[5] = ry as f32;
    }

    fn set_matrix(&self, m: PyArrayLike2<'_, f64, AllowTypeChange>, t: [f64; 3]) -> PyResult<()> {
        let a = m.as_array();
        if a.shape() != [3, 3] {
            return Err(PyValueError::new_err("set_matrix expects a 3x3 matrix"));
        }
        let (rx, ry, rz) = euler_from_cols(|i, j| a[[i, j]]);
        let d = store().row(self.slot);
        d[0] = t[0] as f32;
        d[1] = t[1] as f32;
        d[2] = t[2] as f32;
        d[4] = rx as f32;
        d[5] = ry as f32;
        d[6] = rz as f32;
        Ok(())
    }

    fn __repr__(&self) -> String {
        format!(
            "GameObject(slot={}, mesh_id={})",
            self.slot,
            store().mesh_id(self.slot)
        )
    }
}

fn euler_from_cols(m: impl Fn(usize, usize) -> f64) -> (f64, f64, f64) {
    let sy = (-m(2, 0)).clamp(-1.0, 1.0);
    let y = sy.asin();
    if sy.abs() > 0.99999 {
        (0.0, y, (-m(0, 1)).atan2(m(1, 1)))
    } else {
        (m(2, 1).atan2(m(2, 2)), y, m(1, 0).atan2(m(0, 0)))
    }
}

fn mat3<'py>(py: Python<'py>, m: [[f64; 3]; 3]) -> Bound<'py, PyArray2<f64>> {
    let flat: Vec<f64> = m.iter().flatten().copied().collect();
    PyArray1::from_vec(py, flat).reshape([3, 3]).unwrap()
}

fn rx(a: f64) -> [[f64; 3]; 3] {
    let (s, c) = a.sin_cos();
    [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]
}

fn ry(a: f64) -> [[f64; 3]; 3] {
    let (s, c) = a.sin_cos();
    [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]
}

fn rz(a: f64) -> [[f64; 3]; 3] {
    let (s, c) = a.sin_cos();
    [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
}

pub fn matmul(a: [[f64; 3]; 3], b: [[f64; 3]; 3]) -> [[f64; 3]; 3] {
    let mut o = [[0.0; 3]; 3];
    for i in 0..3 {
        for j in 0..3 {
            o[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j];
        }
    }
    o
}

pub fn camera_rotation(pitch: f64, yaw: f64, roll: f64) -> [[f64; 3]; 3] {
    matmul(matmul(ry(yaw), rx(pitch)), rz(roll))
}

#[pyfunction]
fn rot_x(py: Python<'_>, a: f64) -> Bound<'_, PyArray2<f64>> {
    mat3(py, rx(a))
}

#[pyfunction]
fn rot_y(py: Python<'_>, a: f64) -> Bound<'_, PyArray2<f64>> {
    mat3(py, ry(a))
}

#[pyfunction]
fn rot_z(py: Python<'_>, a: f64) -> Bound<'_, PyArray2<f64>> {
    mat3(py, rz(a))
}

#[pyfunction]
fn euler_from_matrix(m: PyArrayLike2<'_, f64, AllowTypeChange>) -> (f64, f64, f64) {
    let a = m.as_array();
    euler_from_cols(|i, j| a[[i, j]])
}

#[pyfunction]
fn camera_matrix<'py>(py: Python<'py>, rotation: [f64; 3]) -> Bound<'py, PyArray2<f64>> {
    mat3(py, camera_rotation(rotation[0], rotation[1], rotation[2]))
}

#[pyclass(module = "lysyk.engine._native")]
pub struct Camera {
    position: Py<PyArray1<f64>>,
    rotation: Py<PyArray1<f64>>,
    #[pyo3(get, set)]
    pub fov: f64,
    #[pyo3(get, set)]
    pub z_near: f64,
}

pub struct CameraState {
    pub position: [f64; 3],
    pub rotation: [f64; 3],
    pub fov: f64,
    pub z_near: f64,
}

impl Camera {
    pub fn state(&self, py: Python<'_>) -> CameraState {
        let read = |a: &Py<PyArray1<f64>>| {
            let r = a.bind(py).readonly();
            let s = r.as_slice().unwrap();
            [s[0], s[1], s[2]]
        };
        CameraState {
            position: read(&self.position),
            rotation: read(&self.rotation),
            fov: self.fov,
            z_near: self.z_near,
        }
    }
}

fn fill(a: &Py<PyArray1<f64>>, py: Python<'_>, v: [f64; 3]) -> PyResult<()> {
    let mut w = a.bind(py).readwrite();
    let s = w.as_slice_mut()?;
    s.copy_from_slice(&v);
    Ok(())
}

#[pymethods]
impl Camera {
    #[new]
    #[pyo3(signature = (fov=70.0, z_near=0.1))]
    fn new(py: Python<'_>, fov: f64, z_near: f64) -> Self {
        Camera {
            position: PyArray1::from_slice(py, &[0.0, 2.0, -10.0]).unbind(),
            rotation: PyArray1::from_slice(py, &[0.0, 0.0, 0.0]).unbind(),
            fov,
            z_near,
        }
    }

    #[getter]
    fn position(&self, py: Python<'_>) -> Py<PyArray1<f64>> {
        self.position.clone_ref(py)
    }

    #[setter]
    fn set_position(&self, py: Python<'_>, v: [f64; 3]) -> PyResult<()> {
        fill(&self.position, py, v)
    }

    #[getter]
    fn rotation(&self, py: Python<'_>) -> Py<PyArray1<f64>> {
        self.rotation.clone_ref(py)
    }

    #[setter]
    fn set_rotation(&self, py: Python<'_>, v: [f64; 3]) -> PyResult<()> {
        fill(&self.rotation, py, v)
    }

    fn look_at(&self, py: Python<'_>, tx: f64, ty: f64, tz: f64) -> PyResult<()> {
        let st = self.state(py);
        let (dx, dy, dz) = (
            tx - st.position[0],
            ty - st.position[1],
            tz - st.position[2],
        );
        fill(
            &self.rotation,
            py,
            [-(dy.atan2(dx.hypot(dz))), dx.atan2(dz), 0.0],
        )
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<GameObject>()?;
    m.add_class::<Camera>()?;
    m.add("MODE_LIT", MODE_LIT)?;
    m.add("MODE_GLOW", MODE_GLOW)?;
    m.add("MODE_SKY", MODE_SKY)?;
    m.add("MODE_CLOUD", MODE_CLOUD)?;
    m.add("MODE_WATER", MODE_WATER)?;
    m.add_function(wrap_pyfunction!(rot_x, m)?)?;
    m.add_function(wrap_pyfunction!(rot_y, m)?)?;
    m.add_function(wrap_pyfunction!(rot_z, m)?)?;
    m.add_function(wrap_pyfunction!(euler_from_matrix, m)?)?;
    m.add_function(wrap_pyfunction!(camera_matrix, m)?)?;
    Ok(())
}
