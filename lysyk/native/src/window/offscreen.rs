#[pyclass(module = "lysyk.engine._native")]
pub struct OffscreenCore {
    gpu: Arc<Gpu>,
    canvas: Py<Canvas>,
    handle: Py<GpuHandle>,
    texture: wgpu::Texture,
    width: u32,
    height: u32,
}

#[pymethods]
impl OffscreenCore {
    #[new]
    #[pyo3(signature = (width=1280, height=720, msaa=true, api="auto", fonts_dir=""))]
    fn new(
        py: Python<'_>,
        width: u32,
        height: u32,
        msaa: bool,
        api: &str,
        fonts_dir: &str,
    ) -> PyResult<Self> {
        let api = Api::parse(&std::env::var("LYSYK_BACKEND").unwrap_or_else(|_| api.to_string()))?;
        let opened = py.detach(|| open(api, msaa, width, height, &|| None, None))?;
        let gpu = opened.gpu;
        {
            let mut st = gpu.state.lock().unwrap();
            st.format = wgpu::TextureFormat::Rgba8Unorm;
        }
        let texture = gpu.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("offscreen"),
            size: wgpu::Extent3d {
                width,
                height,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
            view_formats: &[],
        });
        let canvas = Py::new(
            py,
            Canvas::new_inner(gpu.clone(), &PathBuf::from(fonts_dir)),
        )?;
        let handle = Py::new(py, GpuHandle { gpu: gpu.clone() })?;
        Ok(OffscreenCore {
            gpu,
            canvas,
            handle,
            texture,
            width,
            height,
        })
    }

    #[getter]
    fn gpu(&self, py: Python<'_>) -> Py<GpuHandle> {
        self.handle.clone_ref(py)
    }

    #[getter]
    fn canvas(&self, py: Python<'_>) -> Py<Canvas> {
        self.canvas.clone_ref(py)
    }

    #[getter]
    fn width(&self) -> u32 {
        self.width
    }

    #[getter]
    fn height(&self) -> u32 {
        self.height
    }

    fn clear(&self, color: (f64, f64, f64)) {
        self.gpu.state.lock().unwrap().clear = [
            (color.0 / 255.0) as f32,
            (color.1 / 255.0) as f32,
            (color.2 / 255.0) as f32,
        ];
    }

    fn set_msaa(&self, enabled: bool) {
        self.gpu.set_msaa(enabled);
    }

    fn frame(&self, py: Python<'_>, draw: &Bound<'_, PyAny>) -> PyResult<()> {
        self.gpu.profiler.begin();
        let mut timer = Timer::start();
        let view = self
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        begin_frame(py, &self.gpu, &self.canvas, view);
        self.gpu.profiler.add(0, timer.lap());
        timer = Timer::start();
        draw.call0()?;
        self.gpu.profiler.add(1, timer.lap());
        end_frame(
            py,
            &self.gpu,
            &self.canvas,
            self.width,
            self.height,
            None,
            None,
        );
        self.gpu.profiler.add(8, 0.0);
        self.gpu.profiler.end();
        Ok(())
    }

    fn read_pixels<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray3<u8>>> {
        let mut enc = self
            .gpu
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("readback"),
            });
        let (buf, bpr) =
            copy_to_buffer(&self.gpu, &mut enc, &self.texture, self.width, self.height);
        self.gpu.queue.submit([enc.finish()]);
        let rb = finish_readback(&self.gpu, &buf, bpr, self.width, self.height, false)
            .map_err(PyRuntimeError::new_err)?;
        PyArray1::from_vec(py, rb.rgba).reshape([self.height as usize, self.width as usize, 4])
    }

    fn save_png(&self, path: &str) -> PyResult<()> {
        let mut enc = self
            .gpu
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("readback"),
            });
        let (buf, bpr) =
            copy_to_buffer(&self.gpu, &mut enc, &self.texture, self.width, self.height);
        self.gpu.queue.submit([enc.finish()]);
        let rb = finish_readback(&self.gpu, &buf, bpr, self.width, self.height, false)
            .map_err(PyRuntimeError::new_err)?;
        write_png(path, rb.width, rb.height, &rb.rgba).map_err(PyRuntimeError::new_err)
    }
}

