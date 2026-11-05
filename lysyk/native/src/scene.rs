use std::collections::HashSet;

use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::object::GameObject;
use crate::store::{store, COL_VISIBLE};

#[derive(Clone, Copy)]
pub struct Entry {
    pub slot: u32,
    pub gid: u32,
    pub center: [f32; 3],
    pub rc: f32,
    pub ro: f32,
    pub cast: bool,
}

#[pyclass(module = "lysyk.engine._native")]
pub struct Scene {
    objects: Py<PyList>,
    dirty: bool,
    entries: Vec<Entry>,
}

impl Scene {
    pub fn rebuild(&mut self, py: Python<'_>) -> PyResult<()> {
        if !self.dirty {
            return Ok(());
        }
        let mut live: Vec<Entry> = Vec::with_capacity(self.objects.bind(py).len());
        for item in self.objects.bind(py).iter() {
            let obj = item.cast::<GameObject>()?.borrow();
            let Some(mesh) = obj.mesh(py) else { continue };
            let m = mesh.bind(py).borrow();
            live.push(Entry {
                slot: obj.slot,
                gid: m.inner.gid,
                center: m.inner.center,
                rc: m.inner.radius_c,
                ro: m.inner.radius_o,
                cast: store().cast(obj.slot),
            });
        }
        live.sort_by_key(|e| e.gid);
        self.entries = live;
        self.dirty = false;
        Ok(())
    }

    pub fn entries(&self) -> &[Entry] {
        &self.entries
    }
}

#[pymethods]
impl Scene {
    #[new]
    fn new(py: Python<'_>) -> Self {
        Scene { objects: PyList::empty(py).unbind(), dirty: true, entries: Vec::new() }
    }

    #[getter]
    fn objects(&self, py: Python<'_>) -> Py<PyList> {
        self.objects.clone_ref(py)
    }

    fn add<'py>(&mut self, obj: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        self.objects.bind(obj.py()).append(&obj)?;
        self.dirty = true;
        Ok(obj)
    }

    pub fn extend(&mut self, py: Python<'_>, objs: &Bound<'_, PyAny>) -> PyResult<()> {
        self.objects.bind(py).call_method1("extend", (objs,))?;
        self.dirty = true;
        Ok(())
    }

    fn remove(&mut self, py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = self.objects.bind(py);
        let target = obj.as_ptr();
        let mut found = None;
        for (i, it) in list.iter().enumerate() {
            if it.as_ptr() == target {
                found = Some(i);
                break;
            }
        }
        if let Some(i) = found {
            list.del_item(i)?;
            self.dirty = true;
        }
        Ok(())
    }

    pub fn remove_many(&mut self, py: Python<'_>, objs: &Bound<'_, PyAny>) -> PyResult<()> {
        let mut drop: HashSet<usize> = HashSet::new();
        for o in objs.try_iter()? {
            drop.insert(o?.as_ptr() as usize);
        }
        let keep = PyList::empty(py);
        for it in self.objects.bind(py).iter() {
            if !drop.contains(&(it.as_ptr() as usize)) {
                keep.append(it)?;
            }
        }
        self.objects = keep.unbind();
        self.dirty = true;
        Ok(())
    }

    fn clear(&mut self, py: Python<'_>) -> PyResult<()> {
        self.objects.bind(py).call_method0("clear")?;
        self.dirty = true;
        Ok(())
    }

    fn invalidate(&mut self) {
        self.dirty = true;
    }

    #[getter]
    fn count(&mut self, py: Python<'_>) -> PyResult<usize> {
        self.rebuild(py)?;
        Ok(self.entries.len())
    }

    #[getter]
    fn visible_count(&mut self, py: Python<'_>) -> PyResult<usize> {
        self.rebuild(py)?;
        Ok(self.entries.iter().filter(|e| store().row(e.slot)[COL_VISIBLE] > 0.5).count())
    }

    fn __len__(&self, py: Python<'_>) -> usize {
        self.objects.bind(py).len()
    }

    fn describe(&mut self, py: Python<'_>) -> PyResult<Vec<(u32, usize, usize, bool)>> {
        self.rebuild(py)?;
        let mut out: Vec<(u32, usize, usize, bool)> = Vec::new();
        for e in &self.entries {
            let tris = crate::mesh::mesh_by_gid(e.gid).map_or(0, |m| m.faces.len());
            let vis = store().row(e.slot)[COL_VISIBLE] > 0.5;
            match out.last_mut() {
                Some(last) if last.0 == e.gid => {
                    last.1 += 1;
                    last.3 |= vis;
                }
                _ => out.push((e.gid, 1, tris, vis)),
            }
        }
        Ok(out)
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Scene>()
}
