impl Renderer {
    fn render_frame(
        &mut self,
        py: Python<'_>,
        camera: &Bound<'_, Camera>,
        scene: &Bound<'_, Scene>,
    ) -> PyResult<()> {
        let mut timer = Timer::start();
        self.poll_shaders(false);
        let cam_state = camera.borrow().state(py);
        let lt_ref = self.lighting.clone_ref(py);
        let lt = lt_ref.bind(py).borrow();
        let mut sc = scene.borrow_mut();
        sc.rebuild(py)?;
        let entries = sc.entries();
        let r = camera_rotation(
            cam_state.rotation[0],
            cam_state.rotation[1],
            cam_state.rotation[2],
        );
        let cam = cam_state.position;
        let (width, height, sample_count, format) = {
            let st = self.gpu.state.lock().unwrap();
            (
                st.width as f64,
                st.height as f64,
                st.sample_count,
                st.format,
            )
        };
        let focal = 0.5 * height / (cam_state.fov.to_radians() * 0.5).tan();
        let tx = width / (2.0 * focal);
        let ty = height / (2.0 * focal);
        let (nx, ny) = ((1.0 + tx * tx).sqrt(), (1.0 + ty * ty).sqrt());
        let far = self.cull_far(lt.fog_density);
        let near = cam_state.z_near;
        let s = store();

        let shadow_on = lt.shadows && self.shadow_quality > 0;
        let res = if shadow_on {
            SHADOW_RES[self.shadow_quality.min(2)]
        } else {
            SHADOW_RES[0]
        };
        self.make_shadow(res);
        let basis = if shadow_on {
            Some(self.fit_shadow(lt.sun_dir(), cam, &r, res))
        } else {
            self.lvp = ident4();
            self.world_texel = 1.0;
            None
        };

        self.staging.clear();
        self.groups.clear();
        self.s_groups.clear();
        self.shadow_staging.clear();
        let mut visible = 0usize;
        let mut triangles = 0usize;
        let half = self.shadow_half;
        let push =
            |buf: &mut Vec<f32>, groups: &mut Vec<(u32, usize, usize)>, gid: u32, row: &[f32]| {
                let n = buf.len() / COLUMNS;
                match groups.last_mut() {
                    Some(g) if g.0 == gid => g.2 += 1,
                    _ => groups.push((gid, n, 1)),
                }
                buf.extend_from_slice(row);
            };

        for e in entries {
            let row = s.row(e.slot);
            if row[COL_VISIBLE] <= 0.5 {
                continue;
            }
            let pos = [row[0] as f64, row[1] as f64, row[2] as f64];
            let scl = [row[8] as f64, row[9] as f64, row[10] as f64];
            let rotated = row[4] != 0.0 || row[5] != 0.0 || row[6] != 0.0;
            let wc = if rotated {
                pos
            } else {
                [
                    pos[0] + e.center[0] as f64 * scl[0],
                    pos[1] + e.center[1] as f64 * scl[1],
                    pos[2] + e.center[2] as f64 * scl[2],
                ]
            };
            let rad = (if rotated { e.ro } else { e.rc }) as f64 * scl[0].max(scl[1]).max(scl[2]);
            let d = [wc[0] - cam[0], wc[1] - cam[1], wc[2] - cam[2]];
            let v = [
                d[0] * r[0][0] + d[1] * r[1][0] + d[2] * r[2][0],
                d[0] * r[0][1] + d[1] * r[1][1] + d[2] * r[2][1],
                d[0] * r[0][2] + d[1] * r[1][2] + d[2] * r[2][2],
            ];
            let z = v[2];
            if z + rad > near
                && v[0].abs() <= tx * z + rad * nx
                && v[1].abs() <= ty * z + rad * ny
                && v[0] * v[0] + v[1] * v[1] + v[2] * v[2] <= (far + rad) * (far + rad)
            {
                push(&mut self.staging, &mut self.groups, e.gid, row);
                visible += 1;
                let t = *self.triangle_cache
                    .entry(e.gid)
                    .or_insert_with(|| mesh_by_gid(e.gid).map_or(0, |m| m.faces.len()));
                triangles += t;
            }
            if let Some((c, right, up, f)) = basis {
                if e.cast {
                    let rel = [wc[0] - c[0], wc[1] - c[1], wc[2] - c[2]];
                    let lx = dot(rel, right);
                    let ly = dot(rel, up);
                    let lz = dot(rel, f);
                    if lx.abs() <= half + rad
                        && ly.abs() <= half + rad
                        && lz + rad >= -SHADOW_BACK
                        && lz - rad <= SHADOW_FRONT
                    {
                push(&mut self.shadow_staging, &mut self.s_groups, e.gid, row);
                    }
                }
            }
        }
        let n_main = self.staging.len() / COLUMNS;
        let n_shadow = self.shadow_staging.len() / COLUMNS;
        self.staging.extend_from_slice(&self.shadow_staging);
        let objects = entries.len();
        drop(sc);
        self.gpu.profiler.add(2, timer.lap());

        let total = n_main + n_shadow;
        if total > 0 {
            if total > self.inst_capacity {
                while self.inst_capacity < total {
                    self.inst_capacity *= 2;
                }
                self.make_instance_buffer();
            }
            self.gpu
                .queue
                .write_buffer(&self.inst_buf, 0, bytemuck::cast_slice(&self.staging));
        }
        let lights = lt.gather_lights(py, cam);
        self.write_globals(py, &lt, &cam_state, &r, shadow_on, &lights, res);
        drop(lt);

        let key = (sample_count, format, self.cull, self.front_face);
        if !self.pipelines.contains_key(&key) {
            let p = self.pipeline_for(&self.shaders, key);
            self.pipelines.insert(key, p);
        }
        if shadow_on && self.shadow_pipeline.is_none() {
            self.shadow_pipeline = Some(self.shadow_pipeline_for(&self.shaders));
        }
        for i in 0..self.groups.len() + self.s_groups.len() {
            let gid = if i < self.groups.len() {
                self.groups[i].0
            } else {
                self.s_groups[i - self.groups.len()].0
            };
            self.gpu_mesh(gid);
        }
        self.gpu.profiler.add(3, timer.lap());

        let gpu = self.gpu.clone();
        let mut st = gpu.state.lock().unwrap();
        if st.encoder.is_none() {
            return Err(PyRuntimeError::new_err(
                "Renderer.render() must be called from on_draw()",
            ));
        }
        if shadow_on {
            let enc = st.encoder.as_mut().unwrap();
            let mut sp = enc.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("shadow"),
                color_attachments: &[],
                depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                    view: self.shadow_view.as_ref().unwrap(),
                    depth_ops: Some(wgpu::Operations {
                        load: wgpu::LoadOp::Clear(1.0),
                        store: wgpu::StoreOp::Store,
                    }),
                    stencil_ops: None,
                }),
                timestamp_writes: None,
                occlusion_query_set: None,
                multiview_mask: None,
            });
            if !self.s_groups.is_empty() {
                sp.set_pipeline(self.shadow_pipeline.as_ref().unwrap());
                sp.set_bind_group(0, &self.shadow_bg, &[]);
                draw(
                    &mut sp,
                    &self.meshes,
                    &self.inst_buf,
                    &self.s_groups,
                    n_main,
                );
            }
        }
        gpu.profiler.add(4, timer.lap());
        {
            let device = &gpu.device;
            if let Some(mut rp) = st.begin_scene_pass(device) {
                if !self.groups.is_empty() {
                    rp.set_pipeline(&self.pipelines[&key]);
                    rp.set_bind_group(0, self.bind_group.as_ref().unwrap(), &[]);
                    draw(&mut rp, &self.meshes, &self.inst_buf, &self.groups, 0);
                }
            }
        }
        gpu.profiler.add(5, timer.lap());
        self.stats = SceneStats {
            draws: self.groups.len(),
            shadow_draws: self.s_groups.len(),
            objects,
            visible,
            shadow_visible: n_shadow,
            triangles,
            lights: lights.len(),
        };
        st.scene_stats = self.stats;
        Ok(())
    }
}
