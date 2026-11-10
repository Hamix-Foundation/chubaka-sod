#[pyclass(dict, module = "lysyk.engine._native")]
pub struct PointLight {
    position: Py<PyArray1<f64>>,
    direction: Option<Py<PyArray1<f64>>>,
    #[pyo3(get, set)]
    pub color: (f64, f64, f64),
    #[pyo3(get, set)]
    pub intensity: f64,
    #[pyo3(get, set)]
    pub radius: f64,
    #[pyo3(get, set)]
    pub cone: Option<f64>,
    #[pyo3(get, set)]
    pub enabled: bool,
}

#[pymethods]
impl PointLight {
    #[new]
    #[pyo3(signature = (position=[0.0, 0.0, 0.0], color=(1.0, 0.95, 0.85), intensity=1.0, radius=30.0, direction=None, cone=None))]
    fn new(
        py: Python<'_>,
        position: [f64; 3],
        color: (f64, f64, f64),
        intensity: f64,
        radius: f64,
        direction: Option<[f64; 3]>,
        cone: Option<f64>,
    ) -> Self {
        PointLight {
            position: PyArray1::from_slice(py, &position).unbind(),
            direction: direction.map(|d| PyArray1::from_slice(py, &d).unbind()),
            color,
            intensity,
            radius,
            cone,
            enabled: true,
        }
    }

    #[getter]
    fn position(&self, py: Python<'_>) -> Py<PyArray1<f64>> {
        self.position.clone_ref(py)
    }

    #[setter]
    fn set_position(&self, py: Python<'_>, v: [f64; 3]) -> PyResult<()> {
        self.position
            .bind(py)
            .readwrite()
            .as_slice_mut()?
            .copy_from_slice(&v);
        Ok(())
    }

    #[getter]
    fn direction(&self, py: Python<'_>) -> Option<Py<PyArray1<f64>>> {
        self.direction.as_ref().map(|d| d.clone_ref(py))
    }

    #[setter]
    fn set_direction(&mut self, py: Python<'_>, v: Option<[f64; 3]>) {
        self.direction = v.map(|d| PyArray1::from_slice(py, &d).unbind());
    }
}

