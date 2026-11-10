#[pymethods]
impl Renderer {
    #[new]
    fn new(py: Python<'_>, window: &Bound<'_, PyAny>, lighting: Py<Lighting>) -> PyResult<Self> {
        let handle: PyRef<crate::window::GpuHandle> = window.getattr("_gpu")?.extract()?;
        let gpu = handle.gpu.clone();
        let _ = py;
        let device = &gpu.device;
        let both = wgpu::ShaderStages::VERTEX | wgpu::ShaderStages::FRAGMENT;
        let bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("scene bgl"),
            entries: &[
                wgpu::BindGroupLayoutEntry {
                    binding: 0,
                    visibility: both,
                    ty: wgpu::BindingType::Buffer {
                        ty: wgpu::BufferBindingType::Uniform,
                        has_dynamic_offset: false,
                        min_binding_size: None,
                    },
                    count: None,
                },
                wgpu::BindGroupLayoutEntry {
                    binding: 1,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Texture {
                        sample_type: wgpu::TextureSampleType::Depth,
                        view_dimension: wgpu::TextureViewDimension::D2,
                        multisampled: false,
                    },
                    count: None,
                },
                wgpu::BindGroupLayoutEntry {
                    binding: 2,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Comparison),
                    count: None,
                },
            ],
        });
        let sbgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("shadow bgl"),
            entries: &[wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::VERTEX,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    has_dynamic_offset: false,
                    min_binding_size: None,
                },
                count: None,
            }],
        });
        let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("scene layout"),
            bind_group_layouts: &[Some(&bgl)],
            immediate_size: 0,
        });
        let slayout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("shadow layout"),
            bind_group_layouts: &[Some(&sbgl)],
            immediate_size: 0,
        });
        let globals = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("globals"),
            size: (GLOBAL_FLOATS * 4) as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let shadow_bg = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("shadow globals"),
            layout: &sbgl,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: globals.as_entire_binding(),
            }],
        });
        let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("shadow sampler"),
            mag_filter: wgpu::FilterMode::Linear,
            min_filter: wgpu::FilterMode::Linear,
            compare: Some(wgpu::CompareFunction::LessEqual),
            ..Default::default()
        });
        let shaders = Shaders {
            main: make_module(device, "main", compose(SHADER_COMMON, SHADER_MAIN)),
            shadow: make_module(device, "shadow", compose(SHADER_COMMON, SHADER_SHADOW)),
        };
        let inst_capacity = 1024;
        let inst_buf = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("instances"),
            size: (inst_capacity * STRIDE) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let mut r = Renderer {
            gpu,
            lighting,
            shadow_quality: 2,
            shadow_half: SHADOW_HALF,
            cull: Some(wgpu::Face::Back),
            front_face: wgpu::FrontFace::Cw,
            cull_name: "back".into(),
            front_name: "cw".into(),
            t0: Instant::now(),
            bgl,
            sbgl,
            layout,
            slayout,
            globals,
            shadow_bg,
            sampler,
            shadow_res: 0,
            shadow_view: None,
            bind_group: None,
            inst_capacity,
            inst_buf,
            shaders,
            pipelines: HashMap::new(),
            shadow_pipeline: None,
            meshes: HashMap::new(),
            triangle_cache: HashMap::new(),
            g: vec![0.0; GLOBAL_FLOATS],
            lvp: ident4(),
            world_texel: 1.0,
            staging: Vec::new(),
            shadow_staging: Vec::new(),
            groups: Vec::new(),
            s_groups: Vec::new(),
            watch: None,
            last_shader_error: None,
            shader_reloads: 0,
            stats: SceneStats::default(),
        };
        let _ = &r.sbgl;
        r.make_shadow(SHADOW_RES[0]);
        if let Ok(dir) = std::env::var("LYSYK_SHADERS") {
            if !dir.is_empty() {
                r.watch_shaders(Some(dir))?;
            }
        }
        Ok(r)
    }

    #[getter]
    fn cull(&self) -> String {
        self.cull_name.clone()
    }

    #[setter]
    fn set_cull(&mut self, v: &str) -> PyResult<()> {
        self.cull = parse_face(v)?;
        self.cull_name = v.to_string();
        Ok(())
    }

    #[getter]
    fn shadow_quality(&self) -> usize {
        self.shadow_quality
    }

    #[setter]
    fn set_shadow_quality(&mut self, v: usize) {
        self.shadow_quality = v.min(3);
    }

    #[getter]
    fn shadow_range(&self) -> f64 {
        self.shadow_half
    }

    #[setter]
    fn set_shadow_range(&mut self, v: f64) {
        self.shadow_half = v.clamp(2.0, 512.0);
    }

    #[getter]
    fn front_face(&self) -> String {
        self.front_name.clone()
    }

    #[setter]
    fn set_front_face(&mut self, v: &str) -> PyResult<()> {
        self.front_face = parse_front(v)?;
        self.front_name = v.to_string();
        Ok(())
    }

    #[getter]
    fn stats<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        d.set_item("draws", self.stats.draws)?;
        d.set_item("shadow_draws", self.stats.shadow_draws)?;
        d.set_item("objects", self.stats.objects)?;
        d.set_item("visible", self.stats.visible)?;
        d.set_item("shadow_visible", self.stats.shadow_visible)?;
        d.set_item("triangles", self.stats.triangles)?;
        d.set_item("lights", self.stats.lights)?;
        d.set_item("gpu_meshes", self.meshes.len())?;
        d.set_item("instance_capacity", self.inst_capacity)?;
        d.set_item("shader_reloads", self.shader_reloads)?;
        Ok(d)
    }

    #[getter]
    fn shader_error(&self) -> Option<String> {
        self.last_shader_error.clone()
    }

    #[pyo3(signature = (directory=None))]
    fn watch_shaders(&mut self, directory: Option<String>) -> PyResult<()> {
        match directory {
            None => {
                self.watch = None;
                Ok(())
            }
            Some(d) => {
                let dir = PathBuf::from(d);
                if !dir.is_dir() {
                    return Err(PyRuntimeError::new_err(format!(
                        "shader directory not found: {}",
                        dir.display()
                    )));
                }
                for name in SHADER_FILES {
                    if !dir.join(name).is_file() {
                        return Err(PyRuntimeError::new_err(format!(
                            "missing {} in {} (run `python -m lysyk.engine dump-shaders {}`)",
                            name,
                            dir.display(),
                            dir.display()
                        )));
                    }
                }
                self.watch = Some(Watch {
                    dir,
                    stamp: HashMap::new(),
                    last_poll: Instant::now(),
                });
                self.poll_shaders(true);
                Ok(())
            }
        }
    }

    fn reload_shaders(&mut self) {
        self.poll_shaders(true);
    }


    fn render(
        &mut self,
        py: Python<'_>,
        camera: &Bound<'_, Camera>,
        scene: &Bound<'_, Scene>,
    ) -> PyResult<()> {
        self.render_frame(py, camera, scene)
    }
}
