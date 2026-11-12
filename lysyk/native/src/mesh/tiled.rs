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
        (
            (x / self.tile).floor() as i64,
            (z / self.tile).floor() as i64,
        )
    }

    fn groups(&self, centers: &[[f32; 2]]) -> Vec<Vec<usize>> {
        let t = self.tile as f32;
        let mut by_code: std::collections::BTreeMap<i64, Vec<usize>> =
            std::collections::BTreeMap::new();
        for (i, c) in centers.iter().enumerate() {
            let tx = (c[0] / t).floor() as i64;
            let tz = (c[1] / t).floor() as i64;
            by_code
                .entry(tx.wrapping_mul(100003).wrapping_add(tz))
                .or_default()
                .push(i);
        }
        by_code.into_values().collect()
    }
}

#[pymethods]
impl TiledBuilder {
    #[new]
    #[pyo3(signature = (tile=256.0))]
    fn new(tile: f64) -> Self {
        TiledBuilder {
            tile,
            order: Vec::new(),
            cells: HashMap::new(),
        }
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
        &mut self,
        py: Python<'_>,
        q: &Bound<'_, PyAny>,
        colors: &Bound<'_, PyAny>,
        facing: &Bound<'_, PyAny>,
        paint: f64,
        glow: bool,
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
                Col::Each(l) if l.len() == q.len() => {
                    Col::Each(sel.iter().map(|&i| l[i]).collect())
                }
                Col::Each(l) => Col::Each(l.clone()),
                Col::Uniform(u) => Col::Uniform(*u),
            };
            let sub_f = match &fac {
                Facing::Each(l) if l.len() == q.len() => {
                    Facing::Each(sel.iter().map(|&i| l[i]).collect())
                }
                Facing::Each(l) => Facing::Each(l.clone()),
                Facing::One(d) => Facing::One(*d),
            };
            cell.bind(py)
                .borrow_mut()
                .quads_impl(&sub_q, &sub_c, &sub_f, paint)?;
        }
        Ok(())
    }

    #[pyo3(signature = (mesh, positions, scales, tints, yaws=None, glow=false))]
    fn instances(
        &mut self,
        py: Python<'_>,
        mesh: &Mesh,
        positions: PyArrayLikeDyn<'_, f32, AllowTypeChange>,
        scales: PyArrayLikeDyn<'_, f32, AllowTypeChange>,
        tints: PyArrayLikeDyn<'_, f32, AllowTypeChange>,
        yaws: Option<PyArrayLikeDyn<'_, f32, AllowTypeChange>>,
        glow: bool,
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
            return Err(PyValueError::new_err(
                "instances: positions, scales, tints and yaws must have the same length",
            ));
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
            cell.bind(py)
                .borrow_mut()
                .instances_impl(&mesh.inner, &p, &s, &tn, y.as_deref());
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
