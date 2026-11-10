use numpy::{AllowTypeChange, PyArrayLikeDyn};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::mesh::Mesh;
use crate::object::{GameObject, MODE_GLOW, MODE_LIT};
use crate::scene::Scene;
use crate::store::{store, COL_COLOR, COL_VISIBLE};

fn flat(obj: &Bound<'_, PyAny>) -> PyResult<Vec<f64>> {
    let a: PyArrayLikeDyn<'_, f64, AllowTypeChange> = obj.extract()?;
    Ok(a.as_array().iter().copied().collect())
}

fn rows3(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<Vec<[f64; 3]>> {
    let f = flat(obj)?;
    if f.is_empty() || f.len() % 3 != 0 {
        return Err(PyValueError::new_err(format!(
            "{name}: expected a 3-vector or an (N, 3) array"
        )));
    }
    Ok(f.chunks_exact(3).map(|c| [c[0], c[1], c[2]]).collect())
}

fn pick<T: Copy>(v: &[T], i: usize, m: usize, name: &str) -> PyResult<T> {
    if v.len() == 1 {
        Ok(v[0])
    } else if v.len() == m {
        Ok(v[i])
    } else {
        Err(PyValueError::new_err(format!(
            "{name}: cannot broadcast {} values to {} particles",
            v.len(),
            m
        )))
    }
}

#[pyclass(module = "lysyk.engine._native")]
pub struct ParticlePool {
    scene: Py<Scene>,
    objects: Py<PyList>,
    slots: Vec<u32>,
    n: usize,
    pos: Vec<[f64; 3]>,
    vel: Vec<[f64; 3]>,
    life: Vec<f64>,
    max_life: Vec<f64>,
    size: Vec<f64>,
    c0: Vec<[f64; 3]>,
    c1: Vec<[f64; 3]>,
    cursor: usize,
    #[pyo3(get, set)]
    gravity: f64,
    #[pyo3(get, set)]
    drag: f64,
    #[pyo3(get, set)]
    rise: f64,
    #[pyo3(get, set)]
    grow: f64,
    #[pyo3(get, set)]
    shrink: f64,
    #[pyo3(get, set)]
    enabled: bool,
}

#[pymethods]
impl ParticlePool {
    #[new]
    #[pyo3(signature = (scene, mesh, count, glow=false, gravity=0.0, drag=0.0, rise=0.0, grow=0.0, shrink=1.0))]
    fn new(
        py: Python<'_>,
        scene: Py<Scene>,
        mesh: Py<Mesh>,
        count: usize,
        glow: bool,
        gravity: f64,
        drag: f64,
        rise: f64,
        grow: f64,
        shrink: f64,
    ) -> PyResult<Self> {
        let mode = if glow { MODE_GLOW } else { MODE_LIT };
        let list = PyList::empty(py);
        let mut slots = Vec::with_capacity(count);
        for _ in 0..count {
            let obj = GameObject::new(
                py,
                Some(mesh.clone_ref(py)),
                None,
                None,
                None,
                None,
                mode,
                false,
                0.0,
            )?;
            slots.push(obj.slot);
            let obj = Py::new(py, obj)?;
            obj.bind(py).borrow().set_visible(false);
            list.append(obj)?;
        }
        scene.bind(py).borrow_mut().extend(py, list.as_any())?;
        Ok(ParticlePool {
            scene,
            objects: list.unbind(),
            slots,
            n: count,
            pos: vec![[0.0; 3]; count],
            vel: vec![[0.0; 3]; count],
            life: vec![0.0; count],
            max_life: vec![1.0; count],
            size: vec![1.0; count],
            c0: vec![[0.0; 3]; count],
            c1: vec![[0.0; 3]; count],
            cursor: 0,
            gravity,
            drag,
            rise,
            grow,
            shrink,
            enabled: true,
        })
    }

    #[getter]
    fn objects(&self, py: Python<'_>) -> Py<PyList> {
        self.objects.clone_ref(py)
    }

    #[getter]
    fn count(&self) -> usize {
        self.n
    }

    #[getter]
    fn alive(&self) -> usize {
        self.life.iter().filter(|l| **l > 0.0).count()
    }

    fn destroy(&mut self, py: Python<'_>) -> PyResult<()> {
        let objs = self.objects.clone_ref(py);
        self.scene
            .bind(py)
            .borrow_mut()
            .remove_many(py, objs.bind(py).as_any())?;
        self.objects = PyList::empty(py).unbind();
        Ok(())
    }

    #[pyo3(signature = (pos, vel, life, size, c0, c1=None))]
    fn emit(
        &mut self,
        pos: &Bound<'_, PyAny>,
        vel: &Bound<'_, PyAny>,
        life: &Bound<'_, PyAny>,
        size: &Bound<'_, PyAny>,
        c0: &Bound<'_, PyAny>,
        c1: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        if !self.enabled || self.n == 0 {
            return Ok(());
        }
        let pos = rows3(pos, "pos")?;
        let m = pos.len();
        let vel = rows3(vel, "vel")?;
        let life = flat(life)?;
        let size = flat(size)?;
        let c0 = rows3(c0, "c0")?;
        let c1 = match c1 {
            Some(c) if !c.is_none() => rows3(c, "c1")?,
            _ => c0.clone(),
        };
        for i in 0..m {
            let idx = (self.cursor + i) % self.n;
            self.pos[idx] = pos[i];
            self.vel[idx] = pick(&vel, i, m, "vel")?;
            let l = pick(&life, i, m, "life")?;
            self.life[idx] = l;
            self.max_life[idx] = l;
            self.size[idx] = pick(&size, i, m, "size")?;
            self.c0[idx] = pick(&c0, i, m, "c0")?;
            self.c1[idx] = pick(&c1, i, m, "c1")?;
        }
        self.cursor = (self.cursor + m) % self.n;
        Ok(())
    }

    fn update(&mut self, dt: f64) {
        let s = store();
        let any_alive = self.life.iter().any(|l| *l > 0.0);
        if !any_alive && !self.slots.iter().any(|&sl| s.row(sl)[COL_VISIBLE] > 0.5) {
            return;
        }
        let damp = (1.0 - self.drag * dt).max(0.0);
        let ay = (self.rise - self.gravity) * dt;
        for i in 0..self.n {
            self.life[i] -= dt;
            let v = &mut self.vel[i];
            v[1] += ay;
            v[0] *= damp;
            v[1] *= damp;
            v[2] *= damp;
            let p = &mut self.pos[i];
            p[0] += v[0] * dt;
            p[1] += v[1] * dt;
            p[2] += v[2] * dt;
            let live = self.life[i] > 0.0;
            let t = (1.0 - self.life[i] / self.max_life[i]).clamp(0.0, 1.0);
            let sc = if live {
                self.size[i] * (1.0 + self.grow * t) * (1.0 - t * t * self.shrink).clamp(0.0, 1.0)
            } else {
                0.0
            };
            let row = s.row(self.slots[i]);
            row[0] = p[0] as f32;
            row[1] = p[1] as f32;
            row[2] = p[2] as f32;
            row[8] = sc as f32;
            row[9] = sc as f32;
            row[10] = sc as f32;
            row[COL_VISIBLE] = if live { 1.0 } else { 0.0 };
            let ch = |k: usize| {
                ((self.c0[i][k] + (self.c1[i][k] - self.c0[i][k]) * t).clamp(0.0, 255.0)) as u32
            };
            s.row_bits(self.slots[i])[COL_COLOR] = ch(0) | (ch(1) << 8) | (ch(2) << 16);
        }
    }

    fn clear(&mut self) {
        let s = store();
        self.life.iter_mut().for_each(|l| *l = 0.0);
        for &sl in &self.slots {
            s.row(sl)[COL_VISIBLE] = 0.0;
        }
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ParticlePool>()
}
