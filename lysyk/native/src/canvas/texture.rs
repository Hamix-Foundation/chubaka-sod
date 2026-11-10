#[pyclass(module = "lysyk.engine._native")]
pub struct Texture {
    pub inner: Arc<TexInner>,
}

fn pixel_bytes(obj: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    if let Ok(a) = obj.extract::<PyReadonlyArrayDyn<'_, u8>>() {
        return Ok(match a.as_slice() {
            Ok(s) => s.to_vec(),
            Err(_) => a.as_array().iter().copied().collect(),
        });
    }
    if let Ok(b) = obj.extract::<PyBackedBytes>() {
        return Ok(b.to_vec());
    }
    Err(PyValueError::new_err(
        "pixel data must be a uint8 numpy array or bytes",
    ))
}

fn write_pixels(
    tex: &TexInner,
    obj: &Bound<'_, PyAny>,
    x: u32,
    y: u32,
    w: u32,
    h: u32,
) -> PyResult<()> {
    let expected = (w as usize) * (h as usize) * 4;
    let size_error = |got: usize| {
        PyValueError::new_err(format!(
            "expected {expected} bytes of RGBA data, got {got}"
        ))
    };
    if let Ok(b) = obj.extract::<PyBackedBytes>() {
        if b.len() != expected {
            return Err(size_error(b.len()));
        }
        tex.write_rgba(x, y, w, h, &b);
        return Ok(());
    }
    if let Ok(a) = obj.extract::<PyReadonlyArrayDyn<'_, u8>>() {
        if let Ok(s) = a.as_slice() {
            if s.len() != expected {
                return Err(size_error(s.len()));
            }
            tex.write_rgba(x, y, w, h, s);
            return Ok(());
        }
        let bytes: Vec<u8> = a.as_array().iter().copied().collect();
        if bytes.len() != expected {
            return Err(size_error(bytes.len()));
        }
        tex.write_rgba(x, y, w, h, &bytes);
        return Ok(());
    }
    Err(PyValueError::new_err(
        "pixel data must be a uint8 numpy array or bytes",
    ))
}

#[pymethods]
impl Texture {
    #[getter]
    fn width(&self) -> u32 {
        self.inner.width
    }

    #[getter]
    fn height(&self) -> u32 {
        self.inner.height
    }

    #[pyo3(signature = (data, x=0, y=0, w=None, h=None))]
    fn update(
        &self,
        data: &Bound<'_, PyAny>,
        x: u32,
        y: u32,
        w: Option<u32>,
        h: Option<u32>,
    ) -> PyResult<()> {
        let w = w.unwrap_or(self.inner.width.saturating_sub(x));
        let h = h.unwrap_or(self.inner.height.saturating_sub(y));
        if x + w > self.inner.width || y + h > self.inner.height || w == 0 || h == 0 {
            return Err(PyValueError::new_err(
                "update region is outside the texture",
            ));
        }
        write_pixels(&self.inner, data, x, y, w, h)
    }

    fn __repr__(&self) -> String {
        format!("Texture({}x{})", self.inner.width, self.inner.height)
    }
}
