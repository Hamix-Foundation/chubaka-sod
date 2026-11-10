impl Renderer {
    fn pipeline_for(
        &self,
        shaders: &Shaders,
        key: (
            u32,
            wgpu::TextureFormat,
            Option<wgpu::Face>,
            wgpu::FrontFace,
        ),
    ) -> wgpu::RenderPipeline {
        let layouts = vertex_layouts();
        self.gpu
            .device
            .create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                label: Some("scene"),
                layout: Some(&self.layout),
                vertex: wgpu::VertexState {
                    module: &shaders.main,
                    entry_point: Some("vs"),
                    compilation_options: Default::default(),
                    buffers: &[Some(layouts[0].clone()), Some(layouts[1].clone())],
                },
                primitive: wgpu::PrimitiveState {
                    topology: wgpu::PrimitiveTopology::TriangleList,
                    cull_mode: key.2,
                    front_face: key.3,
                    ..Default::default()
                },
                depth_stencil: Some(wgpu::DepthStencilState {
                    format: DEPTH_FORMAT,
                    depth_write_enabled: Some(true),
                    depth_compare: Some(wgpu::CompareFunction::Greater),
                    stencil: Default::default(),
                    bias: Default::default(),
                }),
                multisample: wgpu::MultisampleState {
                    count: key.0,
                    mask: !0,
                    alpha_to_coverage_enabled: false,
                },
                fragment: Some(wgpu::FragmentState {
                    module: &shaders.main,
                    entry_point: Some("fs"),
                    compilation_options: Default::default(),
                    targets: &[Some(wgpu::ColorTargetState {
                        format: key.1,
                        blend: None,
                        write_mask: wgpu::ColorWrites::ALL,
                    })],
                }),
                multiview_mask: None,
                cache: None,
            })
    }

    fn shadow_pipeline_for(&self, shaders: &Shaders) -> wgpu::RenderPipeline {
        let layouts = vertex_layouts();
        self.gpu
            .device
            .create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                label: Some("shadow"),
                layout: Some(&self.slayout),
                vertex: wgpu::VertexState {
                    module: &shaders.shadow,
                    entry_point: Some("vs"),
                    compilation_options: Default::default(),
                    buffers: &[Some(layouts[0].clone()), Some(layouts[1].clone())],
                },
                primitive: wgpu::PrimitiveState {
                    topology: wgpu::PrimitiveTopology::TriangleList,
                    cull_mode: None,
                    ..Default::default()
                },
                depth_stencil: Some(wgpu::DepthStencilState {
                    format: DEPTH_FORMAT,
                    depth_write_enabled: Some(true),
                    depth_compare: Some(wgpu::CompareFunction::Less),
                    stencil: Default::default(),
                    bias: Default::default(),
                }),
                multisample: wgpu::MultisampleState::default(),
                fragment: None,
                multiview_mask: None,
                cache: None,
            })
    }

    fn make_shadow(&mut self, res: u32) {
        if res == self.shadow_res && self.shadow_view.is_some() {
            return;
        }
        self.shadow_res = res;
        let tex = self.gpu.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("shadow map"),
            size: wgpu::Extent3d {
                width: res,
                height: res,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: DEPTH_FORMAT,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::TEXTURE_BINDING,
            view_formats: &[],
        });
        let view = tex.create_view(&wgpu::TextureViewDescriptor::default());
        self.bind_group = Some(
            self.gpu
                .device
                .create_bind_group(&wgpu::BindGroupDescriptor {
                    label: Some("globals"),
                    layout: &self.bgl,
                    entries: &[
                        wgpu::BindGroupEntry {
                            binding: 0,
                            resource: self.globals.as_entire_binding(),
                        },
                        wgpu::BindGroupEntry {
                            binding: 1,
                            resource: wgpu::BindingResource::TextureView(&view),
                        },
                        wgpu::BindGroupEntry {
                            binding: 2,
                            resource: wgpu::BindingResource::Sampler(&self.sampler),
                        },
                    ],
                }),
        );
        self.shadow_view = Some(view);
    }

    fn make_instance_buffer(&mut self) {
        self.inst_buf = self.gpu.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("instances"),
            size: (self.inst_capacity * STRIDE) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
    }

    fn gpu_mesh(&mut self, gid: u32) -> Option<&GpuMesh> {
        if !self.meshes.contains_key(&gid) {
            let m: Arc<MeshData> = mesh_by_gid(gid)?;
            let mut vb: Vec<u8> = Vec::with_capacity(m.vertices.len() * 16);
            for (p, c) in m.vertices.iter().zip(m.colors.iter()) {
                for k in 0..3 {
                    vb.extend_from_slice(&p[k].to_le_bytes());
                }
                vb.extend_from_slice(c);
            }
            let idx: Vec<u32> = m.faces.iter().flatten().copied().collect();
            let d = &self.gpu.device;
            let vbuf = d.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("mesh vertices"),
                contents: &vb,
                usage: wgpu::BufferUsages::VERTEX,
            });
            let ibuf = d.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("mesh indices"),
                contents: bytemuck::cast_slice(&idx),
                usage: wgpu::BufferUsages::INDEX,
            });
            self.meshes.insert(
                gid,
                GpuMesh {
                    vbuf,
                    ibuf,
                    index_count: idx.len() as u32,
                    triangles: m.faces.len(),
                },
            );
        }
        self.meshes.get(&gid)
    }

    fn cull_far(&self, fog_density: f64) -> f64 {
        let d = fog_density.max(1e-4);
        (2.35 / d).clamp(350.0, 2600.0)
    }

    fn fit_shadow(&mut self, sun: V3, cam: V3, r: &[[f64; 3]; 3], res: u32) -> (V3, V3, V3, V3) {
        let half = self.shadow_half;
        let f = unit([-sun[0], -sun[1], -sun[2]]);
        let rf: V3 = if f[1].abs() < 0.99 {
            [0.0, 1.0, 0.0]
        } else {
            [0.0, 0.0, 1.0]
        };
        let right = unit(cross(rf, f));
        let up = cross(f, right);
        let fwd = [r[0][2], r[1][2], r[2][2]];
        let mut focus = [
            cam[0] + fwd[0] * half * 0.55,
            0.0,
            cam[2] + fwd[2] * half * 0.55,
        ];
        focus[1] = 0.0;
        let texel = 2.0 * half / res as f64;
        let cx = (dot(focus, right) / texel).floor() * texel;
        let cy = (dot(focus, up) / texel).floor() * texel;
        let cz = dot(focus, f);
        let c = [
            right[0] * cx + up[0] * cy + f[0] * cz,
            right[1] * cx + up[1] * cy + f[1] * cz,
            right[2] * cx + up[2] * cy + f[2] * cz,
        ];
        let zr = SHADOW_BACK + SHADOW_FRONT;
        let mut m = [[0.0; 4]; 4];
        for k in 0..3 {
            m[0][k] = right[k] / half;
            m[1][k] = up[k] / half;
            m[2][k] = f[k] / zr;
        }
        m[0][3] = -dot(right, c) / half;
        m[1][3] = -dot(up, c) / half;
        m[2][3] = (-dot(f, c) + SHADOW_BACK) / zr;
        m[3][3] = 1.0;
        self.lvp = m;
        self.world_texel = texel;
        (c, right, up, f)
    }

    #[allow(clippy::too_many_arguments)]
    fn write_globals(
        &mut self,
        py: Python<'_>,
        lt: &Lighting,
        cam_state: &crate::object::CameraState,
        r: &[[f64; 3]; 3],
        shadow_on: bool,
        lights: &[Gathered],
        res: u32,
    ) {
        let (width, height) = {
            let st = self.gpu.state.lock().unwrap();
            (st.width as f64, st.height as f64)
        };
        let _ = py;
        let cam = cam_state.position;
        let mut view = ident4();
        for i in 0..3 {
            for j in 0..3 {
                view[i][j] = r[j][i];
            }
            view[i][3] = -(r[0][i] * cam[0] + r[1][i] * cam[1] + r[2][i] * cam[2]);
        }
        let focal = 0.5 * height / (cam_state.fov.to_radians() * 0.5).tan();
        let mut proj = [[0.0; 4]; 4];
        proj[0][0] = 2.0 * focal / width;
        proj[1][1] = 2.0 * focal / height;
        proj[2][3] = cam_state.z_near;
        proj[3][2] = 1.0;
        let vp = mul4(&proj, &view);
        let g = &mut self.g;
        for i in 0..4 {
            for j in 0..4 {
                g[j * 4 + i] = vp[i][j] as f32;
                g[16 + j * 4 + i] = self.lvp[i][j] as f32;
            }
        }
        let c = lt.sky_colors();
        let sun = lt.sun_dir();
        let put3 = |g: &mut Vec<f32>, o: usize, v: [f64; 3]| {
            g[o] = v[0] as f32;
            g[o + 1] = v[1] as f32;
            g[o + 2] = v[2] as f32;
        };
        put3(g, 32, cam);
        g[35] = self.t0.elapsed().as_secs_f32();
        put3(g, 36, c.fog);
        g[39] = lt.fog_density as f32;
        put3(g, 40, sun);
        g[43] = 0.0;
        put3(g, 44, c.sun);
        g[47] = if shadow_on { 1.0 } else { 0.0 };
        put3(g, 48, c.sky);
        g[51] = lt.shadow_strength as f32;
        put3(g, 52, c.ground);
        g[55] = 0.0;
        put3(g, 56, c.zenith);
        g[59] = c.stars as f32;
        put3(g, 60, c.horizon);
        g[63] = c.glow as f32;
        g[64] = lights.len() as f32;
        g[65] = lt.exposure as f32;
        g[66] = lt.fog_scatter as f32;
        g[67] = 0.0;
        g[68] = (lt.water_color.0 / 255.0) as f32;
        g[69] = (lt.water_color.1 / 255.0) as f32;
        g[70] = (lt.water_color.2 / 255.0) as f32;
        g[71] = 0.0;
        g[72] = 1.0 / res as f32;
        g[73] = self.world_texel as f32;
        g[74] = if self.shadow_quality >= 2 { 5.0 } else { 1.0 };
        g[75] = 0.0004;
        for (k, l) in lights.iter().enumerate() {
            let o = 76 + 12 * k;
            put3(g, o, l.pos);
            g[o + 3] = l.radius as f32;
            put3(g, o + 4, l.color);
            g[o + 7] = l.intensity as f32;
            match (l.direction, l.cone) {
                (Some(d), Some(cone)) => {
                    put3(g, o + 8, unit(d));
                    g[o + 11] = cone as f32;
                }
                _ => {
                    put3(g, o + 8, [0.0, -1.0, 0.0]);
                    g[o + 11] = -2.0;
                }
            }
        }
        self.gpu
            .queue
            .write_buffer(&self.globals, 0, bytemuck::cast_slice(&self.g));
    }

    fn read_shader(dir: &PathBuf, name: &str) -> Result<String, String> {
        std::fs::read_to_string(dir.join(name))
            .map_err(|e| format!("{}: {e}", dir.join(name).display()))
    }

    fn try_build_shaders(&self, dir: &PathBuf) -> Result<Shaders, String> {
        let common = Self::read_shader(dir, "common.wgsl")?;
        let main = compose(&common, &Self::read_shader(dir, "main.wgsl")?);
        let shadow = compose(&common, &Self::read_shader(dir, "shadow.wgsl")?);
        let device = &self.gpu.device;
        let guard = device.push_error_scope(wgpu::ErrorFilter::Validation);
        let shaders = Shaders {
            main: make_module(device, "main (hot)", main),
            shadow: make_module(device, "shadow (hot)", shadow),
        };
        let (count, format) = {
            let st = self.gpu.state.lock().unwrap();
            (st.sample_count, st.format)
        };
        let _p = self.pipeline_for(&shaders, (count, format, self.cull, self.front_face));
        let _s = self.shadow_pipeline_for(&shaders);
        match pollster::block_on(guard.pop()) {
            None => Ok(shaders),
            Some(e) => Err(e.to_string()),
        }
    }

    fn poll_shaders(&mut self, force: bool) {
        let Some(w) = self.watch.as_mut() else { return };
        if !force && w.last_poll.elapsed().as_secs_f32() < 0.5 {
            return;
        }
        w.last_poll = Instant::now();
        let mut changed = force;
        for name in SHADER_FILES {
            if let Ok(m) = std::fs::metadata(w.dir.join(name)).and_then(|m| m.modified()) {
                if w.stamp.get(name) != Some(&m) {
                    w.stamp.insert(name, m);
                    changed = true;
                }
            }
        }
        if !changed {
            return;
        }
        let dir = w.dir.clone();
        match self.try_build_shaders(&dir) {
            Ok(s) => {
                self.shaders = s;
                self.pipelines.clear();
                self.shadow_pipeline = None;
                self.last_shader_error = None;
                self.shader_reloads += 1;
                log::info!("shaders reloaded from {}", dir.display());
            }
            Err(e) => {
                log::error!("shader reload failed, keeping previous version:\n{e}");
                self.last_shader_error = Some(e);
            }
        }
    }
}

