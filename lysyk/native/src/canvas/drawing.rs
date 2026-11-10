#[pyclass(module = "lysyk.engine._native")]
pub struct Canvas {
    gpu: Arc<Gpu>,
    fonts: FontSet,
    atlas: Atlas,
    pub buf: Vec<[f32; FLOATS]>,
    gpu_buffer: wgpu::Buffer,
    gpu_capacity: usize,
    uniform: wgpu::Buffer,
    bgl: wgpu::BindGroupLayout,
    bind_group: wgpu::BindGroup,
    segs: Vec<(usize, Option<Arc<TexInner>>)>,
    font_ids: HashMap<String, u16>,
    font: u16,
    module: wgpu::ShaderModule,
    pipeline: Option<wgpu::RenderPipeline>,
    pipeline_format: Option<wgpu::TextureFormat>,
    layouts: HashMap<(String, u32, bool, u8, u16), Arc<Layout>>,
    metrics: HashMap<(u32, bool, u16), (f32, f32)>,
    #[pyo3(get, set)]
    pub dt: f64,
    #[pyo3(get, set)]
    pub time: f64,
    uniform_size: (u32, u32),
}

fn px_of(size: f64) -> u32 {
    ((size * 1.45).round() as i64).max(7) as u32
}

impl Canvas {
    pub fn new_inner(gpu: Arc<Gpu>, fonts_dir: &PathBuf) -> Canvas {
        let d = &gpu.device;
        let module = d.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("ui"),
            source: wgpu::ShaderSource::Wgsl(SHADER_UI.into()),
        });
        let bgl = d.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("ui bgl"),
            entries: &[
                wgpu::BindGroupLayoutEntry {
                    binding: 0,
                    visibility: wgpu::ShaderStages::VERTEX,
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
                        sample_type: wgpu::TextureSampleType::Float { filterable: true },
                        view_dimension: wgpu::TextureViewDimension::D2,
                        multisampled: false,
                    },
                    count: None,
                },
                wgpu::BindGroupLayoutEntry {
                    binding: 2,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                    count: None,
                },
            ],
        });
        let uniform = d.create_buffer(&wgpu::BufferDescriptor {
            label: Some("ui uniform"),
            size: 16,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let sampler = d.create_sampler(&wgpu::SamplerDescriptor {
            mag_filter: wgpu::FilterMode::Linear,
            min_filter: wgpu::FilterMode::Linear,
            ..Default::default()
        });
        let atlas = Atlas::new(&gpu);
        let bind_group = d.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("ui bind"),
            layout: &bgl,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: uniform.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::TextureView(&atlas.view),
                },
                wgpu::BindGroupEntry {
                    binding: 2,
                    resource: wgpu::BindingResource::Sampler(&sampler),
                },
            ],
        });
        let cap = 8192;
        let gpu_buffer = d.create_buffer(&wgpu::BufferDescriptor {
            label: Some("ui instances"),
            size: cap as u64 * STRIDE,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let fonts = FontSet::load(fonts_dir);
        drop(sampler);
        Canvas {
            gpu: gpu.clone(),
            fonts,
            atlas,
            buf: Vec::with_capacity(cap),
            gpu_buffer,
            gpu_capacity: cap,
            uniform,
            bgl,
            bind_group,
            segs: Vec::new(),
            font_ids: HashMap::new(),
            font: 0,
            module,
            pipeline: None,
            pipeline_format: None,
            layouts: HashMap::new(),
            metrics: HashMap::new(),
            dt: 0.016,
            time: 0.0,
            uniform_size: (0, 0),
        }
    }

    fn font_id(&self, name: Option<&str>) -> u16 {
        name.and_then(|n| self.font_ids.get(n).copied())
            .unwrap_or(0)
    }

    pub fn begin_frame(&mut self) {
        self.buf.clear();
        self.segs.clear();
        self.time += self.dt;
        if self.atlas.need_reset {
            self.atlas.reset(&self.gpu);
            self.layouts.clear();
        }
    }

    fn put(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        uvr: [f32; 4],
        c1: Rgba,
        c2: Rgba,
        radius: f32,
        border: f32,
        pad: f32,
        kind: f32,
    ) {
        self.buf.push([
            x, y, w, h, uvr[0], uvr[1], uvr[2], uvr[3], c1[0], c1[1], c1[2], c1[3], c2[0], c2[1],
            c2[2], c2[3], radius, border, pad, kind,
        ]);
    }

    const SOLID: [f32; 4] = [0.0, 0.0, 0.002, 0.002];

    pub fn rect_c(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        c1: Rgba,
        radius: f32,
        c2: Option<Rgba>,
    ) {
        self.put(
            x - 1.0,
            y - 1.0,
            w + 2.0,
            h + 2.0,
            Self::SOLID,
            c1,
            c2.unwrap_or(c1),
            radius,
            0.0,
            1.0,
            1.0,
        );
    }

    pub fn outline_c(&mut self, x: f32, y: f32, w: f32, h: f32, c: Rgba, radius: f32, width: f32) {
        self.put(
            x - 1.0,
            y - 1.0,
            w + 2.0,
            h + 2.0,
            Self::SOLID,
            c,
            c,
            radius,
            width,
            1.0,
            2.0,
        );
    }

    pub fn shadow_c(&mut self, x: f32, y: f32, w: f32, h: f32, radius: f32, blur: f32, c: Rgba) {
        self.put(
            x - blur,
            y - blur,
            w + 2.0 * blur,
            h + 2.0 * blur,
            Self::SOLID,
            c,
            c,
            radius,
            0.0,
            blur,
            3.0,
        );
    }

    fn font_metrics(&mut self, px: u32, bold: bool) -> (f32, f32) {
        if let Some(m) = self.metrics.get(&(px, bold, self.font)) {
            return *m;
        }
        let m = match self
            .fonts
            .chain(bold, self.font)
            .first()
            .and_then(|f| f.horizontal_line_metrics(px as f32))
        {
            Some(l) => (l.ascent.ceil(), (l.ascent - l.descent).ceil()),
            None => (px as f32, px as f32 * 1.2),
        };
        self.metrics.insert((px, bold, self.font), m);
        m
    }

    fn glyph(&mut self, ch: char, px: u32, bold: bool) -> Glyph {
        let key = (ch, px, bold, self.font);
        if let Some(g) = self.atlas.glyphs.get(&key) {
            return *g;
        }
        let chain = self.fonts.chain(bold, self.font);
        let fallback = self.fonts.chain(bold, 0);
        let Some(first) = chain.first() else {
            return Glyph {
                adv: px as f32 * 0.5,
                region: None,
            };
        };
        let font = if ch.is_whitespace() {
            first
        } else {
            chain
                .iter()
                .chain(fallback.iter())
                .find(|f| f.lookup_glyph_index(ch) != 0)
                .unwrap_or(first)
        };
        let (m, bitmap) = font.rasterize(ch, px as f32);
        let adv = m.advance_width;
        if ch.is_whitespace() || m.width == 0 || m.height == 0 {
            let g = Glyph { adv, region: None };
            self.atlas.glyphs.insert(key, g);
            return g;
        }
        let (pw, ph) = (m.width as u32 + 2, m.height as u32 + 2);
        if self.atlas.cx + pw + 1 > ATLAS {
            self.atlas.cx = if self.atlas.cy == 0 { 6 } else { 1 };
            self.atlas.cy += self.atlas.row_h + 1;
            self.atlas.row_h = 0;
        }
        if self.atlas.cy + ph + 1 > ATLAS {
            self.atlas.need_reset = true;
            return Glyph { adv, region: None };
        }
        let mut data = vec![0u8; (pw * ph * 4) as usize];
        for y in 0..m.height {
            for x in 0..m.width {
                let a = (bitmap[y * m.width + x] as f32 / 255.0).powf(0.82);
                let o = (((y + 1) as u32 * pw + (x + 1) as u32) * 4) as usize;
                data[o] = 255;
                data[o + 1] = 255;
                data[o + 2] = 255;
                data[o + 3] = (a * 255.0 + 0.5).clamp(0.0, 255.0) as u8;
            }
        }
        let (px0, py0) = (self.atlas.cx, self.atlas.cy);
        self.atlas.write(&self.gpu, px0, py0, pw, ph, &data);
        let s = ATLAS as f32;
        let region = [
            m.xmin as f32 - 1.0,
            -(m.ymin as f32 + m.height as f32) - 1.0,
            pw as f32,
            ph as f32,
            px0 as f32 / s,
            py0 as f32 / s,
            (px0 + pw) as f32 / s,
            (py0 + ph) as f32 / s,
        ];
        self.atlas.cx += pw + 1;
        self.atlas.row_h = self.atlas.row_h.max(ph);
        let g = Glyph {
            adv,
            region: Some(region),
        };
        self.atlas.glyphs.insert(key, g);
        g
    }

    fn layout(&mut self, text: &str, px: u32, bold: bool, anchor: u8) -> Arc<Layout> {
        let key = (text.to_string(), px, bold, anchor, self.font);
        if let Some(l) = self.layouts.get(&key) {
            return l.clone();
        }
        let (asc, line_h) = self.font_metrics(px, bold);
        let mut rows = Vec::new();
        let mut width = 0.0f32;
        let lines: Vec<&str> = text.split('\n').collect();
        for (li, line) in lines.iter().enumerate() {
            let chars: Vec<char> = line.chars().collect();
            let glyphs: Vec<Glyph> = chars.iter().map(|c| self.glyph(*c, px, bold)).collect();
            let total: f32 = glyphs.iter().map(|g| g.adv).sum();
            width = width.max(total);
            let mut pen = match anchor {
                1 => -total * 0.5,
                2 => -total,
                _ => 0.0,
            };
            let base = asc + li as f32 * line_h;
            for g in glyphs {
                if let Some(r) = g.region {
                    rows.push([
                        (pen + r[0]).round(),
                        (base + r[1]).round(),
                        r[2],
                        r[3],
                        r[4],
                        r[5],
                        r[6],
                        r[7],
                        1.0,
                        1.0,
                        1.0,
                        1.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                    ]);
                }
                pen += g.adv;
            }
        }
        let l = Arc::new(Layout {
            rows,
            width,
            height: line_h * lines.len() as f32,
        });
        if !self.atlas.need_reset {
            if self.layouts.len() > 4096 {
                self.layouts.clear();
            }
            self.layouts.insert(key, l.clone());
        }
        l
    }

    #[allow(clippy::too_many_arguments)]
    pub fn text_c(
        &mut self,
        text: &str,
        x: f32,
        y: f32,
        color: Rgba,
        size: f64,
        anchor_x: u8,
        anchor_y: u8,
        bold: bool,
        shadow: bool,
    ) {
        let l = self.layout(text, px_of(size), bold, anchor_x);
        if l.rows.is_empty() {
            return;
        }
        let y = match anchor_y {
            1 => y - l.height * 0.5,
            2 => y - l.height,
            _ => y,
        };
        if shadow {
            let off = (size as f32 * 0.07).max(1.0);
            let sc = [0.0, 0.0, 0.0, 0.55 * color[3]];
            for r in &l.rows {
                let mut s = *r;
                s[0] += (x + off).round();
                s[1] += (y + off).round();
                s[8..12].copy_from_slice(&sc);
                self.buf.push(s);
            }
        }
        for r in &l.rows {
            let mut s = *r;
            s[0] += x.round();
            s[1] += y.round();
            s[8..12].copy_from_slice(&color);
            self.buf.push(s);
        }
    }

    fn make_texture(
        &self,
        width: u32,
        height: u32,
        data: Option<&[u8]>,
        nearest: bool,
        repeat: bool,
    ) -> PyResult<Texture> {
        if width == 0 || height == 0 || width > 8192 || height > 8192 {
            return Err(PyValueError::new_err(
                "texture size must be between 1 and 8192",
            ));
        }
        let d = &self.gpu.device;
        let texture = d.create_texture(&wgpu::TextureDescriptor {
            label: Some("lysyk texture"),
            size: wgpu::Extent3d {
                width,
                height,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let filter = if nearest {
            wgpu::FilterMode::Nearest
        } else {
            wgpu::FilterMode::Linear
        };
        let address = if repeat {
            wgpu::AddressMode::Repeat
        } else {
            wgpu::AddressMode::ClampToEdge
        };
        let sampler = d.create_sampler(&wgpu::SamplerDescriptor {
            mag_filter: filter,
            min_filter: filter,
            address_mode_u: address,
            address_mode_v: address,
            ..Default::default()
        });
        let bind_group = d.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("lysyk texture bind"),
            layout: &self.bgl,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: self.uniform.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::TextureView(&view),
                },
                wgpu::BindGroupEntry {
                    binding: 2,
                    resource: wgpu::BindingResource::Sampler(&sampler),
                },
            ],
        });
        let inner = Arc::new(TexInner {
            gpu: self.gpu.clone(),
            texture,
            bind_group,
            width,
            height,
        });
        let blank;
        let pixels: &[u8] = match data {
            Some(b) => b,
            None => {
                blank = vec![0u8; (width * height * 4) as usize];
                &blank
            }
        };
        inner.write_rgba(0, 0, width, height, pixels);
        Ok(Texture { inner })
    }

    pub fn text_size(&mut self, text: &str, size: f64, bold: bool) -> (f32, f32) {
        let l = self.layout(text, px_of(size), bold, 0);
        (l.width, l.height)
    }

    pub fn flush(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        target: &wgpu::TextureView,
        width: u32,
        height: u32,
        format: wgpu::TextureFormat,
    ) {
        let n = self.buf.len();
        if n == 0 {
            return;
        }
        if self.pipeline_format != Some(format) {
            let d = &self.gpu.device;
            let attrs: Vec<wgpu::VertexAttribute> = (0..5)
                .map(|k| wgpu::VertexAttribute {
                    format: wgpu::VertexFormat::Float32x4,
                    offset: 16 * k as u64,
                    shader_location: k as u32,
                })
                .collect();
            let layout = d.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
                label: Some("ui layout"),
                bind_group_layouts: &[Some(&self.bgl)],
                immediate_size: 0,
            });
            let blend = wgpu::BlendState {
                color: wgpu::BlendComponent {
                    src_factor: wgpu::BlendFactor::SrcAlpha,
                    dst_factor: wgpu::BlendFactor::OneMinusSrcAlpha,
                    operation: wgpu::BlendOperation::Add,
                },
                alpha: wgpu::BlendComponent {
                    src_factor: wgpu::BlendFactor::One,
                    dst_factor: wgpu::BlendFactor::OneMinusSrcAlpha,
                    operation: wgpu::BlendOperation::Add,
                },
            };
            self.pipeline = Some(d.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                label: Some("ui"),
                layout: Some(&layout),
                vertex: wgpu::VertexState {
                    module: &self.module,
                    entry_point: Some("vs"),
                    compilation_options: Default::default(),
                    buffers: &[Some(wgpu::VertexBufferLayout {
                        array_stride: STRIDE,
                        step_mode: wgpu::VertexStepMode::Instance,
                        attributes: &attrs,
                    })],
                },
                primitive: wgpu::PrimitiveState::default(),
                depth_stencil: None,
                multisample: wgpu::MultisampleState::default(),
                fragment: Some(wgpu::FragmentState {
                    module: &self.module,
                    entry_point: Some("fs"),
                    compilation_options: Default::default(),
                    targets: &[Some(wgpu::ColorTargetState {
                        format,
                        blend: Some(blend),
                        write_mask: wgpu::ColorWrites::ALL,
                    })],
                }),
                multiview_mask: None,
                cache: None,
            }));
            self.pipeline_format = Some(format);
        }
        if n > self.gpu_capacity {
            while self.gpu_capacity < n {
                self.gpu_capacity *= 2;
            }
            self.gpu_buffer = self.gpu.device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("ui instances"),
                size: self.gpu_capacity as u64 * STRIDE,
                usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
        }
        let q = &self.gpu.queue;
        q.write_buffer(&self.gpu_buffer, 0, bytemuck::cast_slice(&self.buf));
        if self.uniform_size != (width, height) {
            q.write_buffer(
                &self.uniform,
                0,
                bytemuck::cast_slice(&[width as f32, height as f32, 0.0f32, 0.0f32]),
            );
            self.uniform_size = (width, height);
        }
        let mut rp = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("ui"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view: target,
                depth_slice: None,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Load,
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
            multiview_mask: None,
        });
        rp.set_pipeline(self.pipeline.as_ref().unwrap());
        rp.set_vertex_buffer(0, self.gpu_buffer.slice(..));
        let mut start = 0usize;
        let mut current: Option<&Arc<TexInner>> = None;
        for (idx, tex) in self.segs.iter().chain(std::iter::once(&(n, None))) {
            let idx = (*idx).min(n);
            if idx > start {
                match current {
                    Some(t) => rp.set_bind_group(0, &t.bind_group, &[]),
                    None => rp.set_bind_group(0, &self.bind_group, &[]),
                }
                rp.draw(0..6, start as u32..idx as u32);
            }
            start = idx;
            current = tex.as_ref();
        }
        drop(rp);
        self.buf.clear();
        self.segs.clear();
    }
}

fn decode_png(path: &str) -> PyResult<(u32, u32, Vec<u8>)> {
    let file = std::fs::File::open(path).map_err(|e| PyIOError::new_err(format!("{path}: {e}")))?;
    let mut dec = png::Decoder::new(std::io::BufReader::new(file));
    dec.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = dec
        .read_info()
        .map_err(|e| PyRuntimeError::new_err(format!("{path}: {e}")))?;
    let mut buf = vec![
        0u8;
        reader
            .output_buffer_size()
            .ok_or_else(|| PyRuntimeError::new_err("image too large"))?
    ];
    let info = reader
        .next_frame(&mut buf)
        .map_err(|e| PyRuntimeError::new_err(format!("{path}: {e}")))?;
    let (w, h) = (info.width, info.height);
    let ch = info.color_type.samples();
    let mut rgba = vec![255u8; (w * h * 4) as usize];
    for i in 0..(w * h) as usize {
        let p = &buf[i * ch..i * ch + ch];
        let px = match ch {
            1 => [p[0], p[0], p[0], 255],
            2 => [p[0], p[0], p[0], p[1]],
            3 => [p[0], p[1], p[2], 255],
            _ => [p[0], p[1], p[2], p[3]],
        };
        rgba[i * 4..i * 4 + 4].copy_from_slice(&px);
    }
    Ok((w, h, rgba))
}

fn ax_code(s: &str) -> u8 {
    match s {
        "center" => 1,
        "right" => 2,
        _ => 0,
    }
}

fn ay_code(s: &str) -> u8 {
    match s {
        "center" => 1,
        "bottom" => 2,
        _ => 0,
    }
}

#[pymethods]
impl Canvas {
    #[pyo3(signature = (x, y, w, h, color, radius=0.0, color2=None))]
    fn rect(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        color: &Bound<'_, PyAny>,
        radius: f32,
        color2: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let c1 = parse_color(color)?;
        let c2 = match color2 {
            Some(c) if !c.is_none() => Some(parse_color(c)?),
            _ => None,
        };
        self.rect_c(x, y, w, h, c1, radius, c2);
        Ok(())
    }

    #[pyo3(signature = (x, y, w, h, color, radius=0.0, width=1.0))]
    fn outline(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        color: &Bound<'_, PyAny>,
        radius: f32,
        width: f32,
    ) -> PyResult<()> {
        let c = parse_color(color)?;
        self.outline_c(x, y, w, h, c, radius, width);
        Ok(())
    }

    #[pyo3(signature = (x, y, w, h, color, border=1.0))]
    fn rect_outline(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        color: &Bound<'_, PyAny>,
        border: f32,
    ) -> PyResult<()> {
        let c = parse_color(color)?;
        self.outline_c(x, y, w, h, c, 0.0, border);
        Ok(())
    }

    #[pyo3(signature = (x, y, w, h, top, bottom, steps=0))]
    fn gradient_v(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        top: &Bound<'_, PyAny>,
        bottom: &Bound<'_, PyAny>,
        steps: i32,
    ) -> PyResult<()> {
        let _ = steps;
        let (a, b) = (parse_color(top)?, parse_color(bottom)?);
        self.rect_c(x, y, w, h, a, 0.0, Some(b));
        Ok(())
    }

    fn shadow(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        radius: f32,
        blur: f32,
        color: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let c = parse_color(color)?;
        self.shadow_c(x, y, w, h, radius, blur, c);
        Ok(())
    }

    #[pyo3(signature = (cx, cy, r, color, color2=None))]
    fn circle(
        &mut self,
        cx: f32,
        cy: f32,
        r: f32,
        color: &Bound<'_, PyAny>,
        color2: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        self.rect(cx - r, cy - r, 2.0 * r, 2.0 * r, color, r, color2)
    }

    #[allow(clippy::too_many_arguments)]
    fn arc(
        &mut self,
        cx: f32,
        cy: f32,
        radius: f32,
        thickness: f32,
        start: f32,
        sweep: f32,
        frac: f32,
        fill: &Bound<'_, PyAny>,
        track: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let (c1, c2) = (parse_color(fill)?, parse_color(track)?);
        let size = 2.0 * (radius + 1.0);
        self.put(
            cx - radius - 1.0,
            cy - radius - 1.0,
            size,
            size,
            [start, sweep, frac, 0.0],
            c1,
            c2,
            0.0,
            thickness,
            1.0,
            4.0,
        );
        Ok(())
    }

    #[pyo3(signature = (x, y, w, h, radius, fill, edge=None, blur=18.0, drop=0.35, top=None))]
    #[allow(clippy::too_many_arguments)]
    fn panel(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        radius: f32,
        fill: &Bound<'_, PyAny>,
        edge: Option<&Bound<'_, PyAny>>,
        blur: f32,
        drop: f32,
        top: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let f = parse_color(fill)?;
        if drop > 0.0 {
            self.shadow_c(
                x,
                y + blur * 0.35,
                w,
                h,
                radius,
                blur,
                [0.0, 0.0, 0.0, (255.0 * drop).floor() / 255.0],
            );
        }
        let t = match top {
            Some(t) if !t.is_none() => parse_color(t)?,
            _ => f,
        };
        self.rect_c(x, y, w, h, t, radius, Some(f));
        if let Some(e) = edge {
            if !e.is_none() {
                let ec = parse_color(e)?;
                self.outline_c(x, y, w, h, ec, radius, 1.0);
            }
        }
        Ok(())
    }

    #[pyo3(signature = (text, size=14.0, bold=false, font=None))]
    fn text_width(
        &mut self,
        text: &Bound<'_, PyAny>,
        size: f64,
        bold: bool,
        font: Option<&str>,
    ) -> PyResult<f32> {
        self.font = self.font_id(font);
        let r = self.text_size(&text.str()?.to_string_lossy(), size, bold).0;
        self.font = 0;
        Ok(r)
    }

    #[pyo3(signature = (text, size=14.0, bold=false, font=None))]
    fn text_height(
        &mut self,
        text: &Bound<'_, PyAny>,
        size: f64,
        bold: bool,
        font: Option<&str>,
    ) -> PyResult<f32> {
        self.font = self.font_id(font);
        let r = self.text_size(&text.str()?.to_string_lossy(), size, bold).1;
        self.font = 0;
        Ok(r)
    }

    #[pyo3(signature = (text, x, y, color, size=14.0, anchor_x="left", anchor_y="top", bold=false, shadow=false, font=None))]
    #[allow(clippy::too_many_arguments)]
    fn text(
        &mut self,
        text: &Bound<'_, PyAny>,
        x: f32,
        y: f32,
        color: &Bound<'_, PyAny>,
        size: f64,
        anchor_x: &str,
        anchor_y: &str,
        bold: bool,
        shadow: bool,
        font: Option<&str>,
    ) -> PyResult<()> {
        let c = parse_color(color)?;
        let t = text.str()?.to_string_lossy().into_owned();
        self.font = self.font_id(font);
        self.text_c(
            &t,
            x,
            y,
            c,
            size,
            ax_code(anchor_x),
            ay_code(anchor_y),
            bold,
            shadow,
        );
        self.font = 0;
        Ok(())
    }

    fn load_font(&mut self, name: &str, path: &str) -> PyResult<()> {
        let bytes = std::fs::read(path).map_err(|e| PyIOError::new_err(format!("{path}: {e}")))?;
        let font = fontdue::Font::from_bytes(bytes, fontdue::FontSettings::default())
            .map_err(|e| PyRuntimeError::new_err(format!("{path}: {e}")))?;
        match self.font_ids.get(name) {
            Some(id) => self.fonts.custom[*id as usize - 1] = vec![font],
            None => {
                self.fonts.custom.push(vec![font]);
                self.font_ids
                    .insert(name.to_string(), self.fonts.custom.len() as u16);
            }
        }
        self.layouts.clear();
        Ok(())
    }

    fn has_font(&self, name: &str) -> bool {
        self.font_ids.contains_key(name)
    }

    #[pyo3(signature = (width, height, data=None, filter="linear", repeat=false))]
    fn texture(
        &self,
        width: u32,
        height: u32,
        data: Option<&Bound<'_, PyAny>>,
        filter: &str,
        repeat: bool,
    ) -> PyResult<Texture> {
        let bytes = match data {
            Some(d) if !d.is_none() => {
                let b = pixel_bytes(d)?;
                if b.len() != (width as usize) * (height as usize) * 4 {
                    return Err(PyValueError::new_err(format!(
                        "expected {} bytes of RGBA data, got {}",
                        width as usize * height as usize * 4,
                        b.len()
                    )));
                }
                Some(b)
            }
            _ => None,
        };
        self.make_texture(width, height, bytes.as_deref(), filter == "nearest", repeat)
    }

    #[pyo3(signature = (path, filter="linear", repeat=false))]
    fn load_texture(&self, path: &str, filter: &str, repeat: bool) -> PyResult<Texture> {
        let (w, h, rgba) = decode_png(path)?;
        self.make_texture(w, h, Some(&rgba), filter == "nearest", repeat)
    }

    #[pyo3(signature = (tex, x, y, w, h, tint=None, uv=None))]
    #[allow(clippy::too_many_arguments)]
    fn image(
        &mut self,
        tex: &Bound<'_, Texture>,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        tint: Option<&Bound<'_, PyAny>>,
        uv: Option<(f32, f32, f32, f32)>,
    ) -> PyResult<()> {
        let c = match tint {
            Some(t) if !t.is_none() => parse_color(t)?,
            _ => [1.0, 1.0, 1.0, 1.0],
        };
        let (u0, v0, u1, v1) = uv.unwrap_or((0.0, 0.0, 1.0, 1.0));
        let inner = tex.borrow().inner.clone();
        self.segs.push((self.buf.len(), Some(inner)));
        self.put(x, y, w, h, [u0, v0, u1, v1], c, c, 0.0, 0.0, 0.0, 0.0);
        self.segs.push((self.buf.len(), None));
        Ok(())
    }

    #[getter]
    fn instance_count(&self) -> usize {
        self.buf.len()
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Canvas>()?;
    m.add_class::<Texture>()
}
