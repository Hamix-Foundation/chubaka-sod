#[derive(Clone, Copy)]
pub struct Gathered {
    pub pos: [f64; 3],
    pub color: [f64; 3],
    pub intensity: f64,
    pub radius: f64,
    pub direction: Option<[f64; 3]>,
    pub cone: Option<f64>,
}

pub struct SkyColors {
    pub zenith: [f64; 3],
    pub horizon: [f64; 3],
    pub fog: [f64; 3],
    pub sun: [f64; 3],
    pub sky: [f64; 3],
    pub ground: [f64; 3],
    pub stars: f64,
    pub glow: f64,
}

#[pyclass(module = "lysyk.engine._native")]
pub struct Lighting {
    #[pyo3(get, set)]
    pub shadows: bool,
    #[pyo3(get)]
    pub hour: f64,
    #[pyo3(get, set)]
    pub azimuth: f64,
    #[pyo3(get, set)]
    pub fog_density: f64,
    #[pyo3(get, set)]
    pub fog_tint: (f64, f64, f64),
    #[pyo3(get, set)]
    pub sky_tint: (f64, f64, f64),
    #[pyo3(get, set)]
    pub sun_scale: f64,
    #[pyo3(get, set)]
    pub ambient_scale: f64,
    #[pyo3(get, set)]
    pub exposure: f64,
    #[pyo3(get, set)]
    pub shadow_strength: f64,
    #[pyo3(get, set)]
    pub water_color: (f64, f64, f64),
    #[pyo3(get, set)]
    pub fog_scatter: f64,
    #[pyo3(get, set)]
    pub stars_scale: f64,
    #[pyo3(get, set)]
    pub elevation: f64,
    #[pyo3(get, set)]
    pub night_factor: f64,
    #[pyo3(get, set)]
    pub static_intensity: f64,
    #[pyo3(get, set)]
    pub static_radius: f64,
    #[pyo3(get, set)]
    pub static_enabled: bool,
    lights: Py<PyList>,
    static_pos: Vec<[f64; 3]>,
    static_color: [f64; 3],
    manual: Option<Key>,
    key: Key,
    sky_c: [f64; 3],
    hor_c: [f64; 3],
    fog_c: [f64; 3],
}

fn mul3(a: [f64; 3], t: (f64, f64, f64)) -> [f64; 3] {
    [a[0] * t.0, a[1] * t.1, a[2] * t.2]
}

impl Lighting {
    fn resolve(&mut self, manual: bool) {
        let key = if manual && self.manual.is_some() {
            self.manual.unwrap()
        } else {
            let h = self.hour;
            let mut found = KEY_END;
            for i in 0..KEYS.len() {
                let (h0, k0) = &KEYS[i];
                let (h1, k1) = if i + 1 < KEYS.len() {
                    (KEYS[i + 1].0, KEYS[i + 1].1)
                } else {
                    (24.0, KEY_END)
                };
                if *h0 <= h && h <= h1 {
                    found = lerp_key(k0, &k1, smooth((h - h0) / (h1 - h0)));
                    break;
                }
            }
            let e = 62.0 * (std::f64::consts::PI * (h - 6.0) / 13.0).sin();
            let w = smooth(((e + 6.0) / 10.0).clamp(0.0, 1.0));
            self.night_factor = 1.0 - w;
            let day_e = e.max(9.0);
            self.elevation = day_e * w + 42.0 * (1.0 - w);
            found
        };
        self.key = key;
        self.sky_c = mul3(key.zenith, self.sky_tint);
        self.hor_c = mul3(key.horizon, self.sky_tint);
        self.fog_c = mul3(key.fog, self.fog_tint);
    }

    pub fn sun_dir(&self) -> [f64; 3] {
        let az = self.azimuth.to_radians();
        let el = self.elevation.to_radians();
        let c = el.cos();
        [c * az.sin(), el.sin(), c * az.cos()]
    }

    pub fn sky_colors(&self) -> SkyColors {
        let k = &self.key;
        let s = [
            k.sun[0] * k.sun[3] * self.sun_scale,
            k.sun[1] * k.sun[3] * self.sun_scale,
            k.sun[2] * k.sun[3] * self.sun_scale,
        ];
        let amb = |c: [f64; 3]| {
            [
                c[0] * self.ambient_scale,
                c[1] * self.ambient_scale,
                c[2] * self.ambient_scale,
            ]
        };
        let n = |c: [f64; 3]| [c[0] / 255.0, c[1] / 255.0, c[2] / 255.0];
        SkyColors {
            zenith: n(self.sky_c),
            horizon: n(self.hor_c),
            fog: n(self.fog_c),
            sun: s,
            sky: amb(k.sky),
            ground: amb(k.ground),
            stars: k.stars * self.stars_scale,
            glow: k.glow,
        }
    }

    pub fn gather_lights(&self, py: Python<'_>, cam: [f64; 3]) -> Vec<Gathered> {
        let mut out: Vec<Gathered> = Vec::with_capacity(MAX_LIGHTS);
        for item in self.lights.bind(py).iter() {
            if out.len() >= MAX_LIGHTS {
                break;
            }
            let Ok(l) = item.cast::<PointLight>() else {
                continue;
            };
            let l = l.borrow();
            if !l.enabled {
                continue;
            }
            let rd = |a: &Py<PyArray1<f64>>| {
                let r = a.bind(py).readonly();
                let s = r.as_slice().unwrap();
                [s[0], s[1], s[2]]
            };
            out.push(Gathered {
                pos: rd(&l.position),
                color: [l.color.0, l.color.1, l.color.2],
                intensity: l.intensity,
                radius: l.radius,
                direction: l.direction.as_ref().map(|d| rd(d)),
                cone: l.cone,
            });
        }
        let room = MAX_LIGHTS.saturating_sub(out.len());
        if room > 0 && self.static_enabled && !self.static_pos.is_empty() {
            let lim = (self.static_radius * 2.2).powi(2);
            let mut near: Vec<(f64, usize)> = self
                .static_pos
                .iter()
                .enumerate()
                .map(|(i, p)| {
                    (
                        (p[0] - cam[0]).powi(2) + (p[1] - cam[1]).powi(2) + (p[2] - cam[2]).powi(2),
                        i,
                    )
                })
                .filter(|(d, _)| *d < lim)
                .collect();
            if near.len() > room {
                near.select_nth_unstable_by(room - 1, |a, b| a.0.partial_cmp(&b.0).unwrap());
                near.truncate(room);
            }
            for (_, i) in near {
                out.push(Gathered {
                    pos: self.static_pos[i],
                    color: self.static_color,
                    intensity: self.static_intensity,
                    radius: self.static_radius,
                    direction: None,
                    cone: None,
                });
            }
        }
        out.truncate(MAX_LIGHTS);
        out
    }
}

fn tuple3(t: [f64; 3]) -> (f64, f64, f64) {
    (t[0], t[1], t[2])
}

#[pymethods]
impl Lighting {
    #[new]
    fn new(py: Python<'_>) -> Self {
        let mut l = Lighting {
            shadows: true,
            hour: 12.0,
            azimuth: 215.0,
            fog_density: 0.0021,
            fog_tint: (1.0, 1.0, 1.0),
            sky_tint: (1.0, 1.0, 1.0),
            sun_scale: 1.0,
            ambient_scale: 1.0,
            exposure: 1.0,
            shadow_strength: 0.82,
            water_color: (18.0, 78.0, 118.0),
            fog_scatter: 1.0,
            stars_scale: 1.0,
            elevation: 45.0,
            night_factor: 0.0,
            static_intensity: 1.0,
            static_radius: 30.0,
            static_enabled: true,
            lights: PyList::empty(py).unbind(),
            static_pos: Vec::new(),
            static_color: [1.0, 1.0, 1.0],
            manual: None,
            key: KEY_END,
            sky_c: [0.0; 3],
            hor_c: [0.0; 3],
            fog_c: [0.0; 3],
        };
        l.set_hour(12.0);
        l
    }

    #[getter]
    fn lights(&self, py: Python<'_>) -> Py<PyList> {
        self.lights.clone_ref(py)
    }

    #[getter]
    fn manual(&self) -> bool {
        self.manual.is_some()
    }

    fn set_hour(&mut self, hour: f64) {
        self.hour = hour.rem_euclid(24.0);
        self.manual = None;
        self.resolve(false);
    }

    fn advance(&mut self, hours: f64) {
        self.set_hour(self.hour + hours);
    }

    #[pyo3(signature = (zenith, horizon, fog, sun_color, sun_intensity, sky_ambient, ground_ambient, elevation, azimuth, stars=0.0, glow=0.3))]
    fn set_manual(
        &mut self,
        zenith: [f64; 3],
        horizon: [f64; 3],
        fog: [f64; 3],
        sun_color: [f64; 3],
        sun_intensity: f64,
        sky_ambient: [f64; 3],
        ground_ambient: [f64; 3],
        elevation: f64,
        azimuth: f64,
        stars: f64,
        glow: f64,
    ) {
        self.manual = Some(Key {
            zenith,
            horizon,
            fog,
            sun: [sun_color[0], sun_color[1], sun_color[2], sun_intensity],
            sky: sky_ambient,
            ground: ground_ambient,
            stars,
            glow,
        });
        self.elevation = elevation;
        self.azimuth = azimuth;
        self.night_factor = 0.0;
        self.resolve(true);
    }

    fn refresh(&mut self) {
        let m = self.manual.is_some();
        self.resolve(m);
    }

    fn sun_direction(&self) -> (f64, f64, f64) {
        tuple3(self.sun_dir())
    }

    fn colors<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let c = self.sky_colors();
        let d = PyDict::new(py);
        d.set_item("zenith", tuple3(c.zenith))?;
        d.set_item("horizon", tuple3(c.horizon))?;
        d.set_item("fog", tuple3(c.fog))?;
        d.set_item("sun", tuple3(c.sun))?;
        d.set_item("sky", tuple3(c.sky))?;
        d.set_item("ground", tuple3(c.ground))?;
        d.set_item("stars", c.stars)?;
        d.set_item("glow", c.glow)?;
        Ok(d)
    }

    fn clear_color(&self) -> (i32, i32, i32) {
        (
            self.fog_c[0] as i32,
            self.fog_c[1] as i32,
            self.fog_c[2] as i32,
        )
    }

    fn add_light<'py>(&self, light: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        self.lights.bind(light.py()).append(&light)?;
        Ok(light)
    }

    fn remove_light(&self, py: Python<'_>, light: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = self.lights.bind(py);
        let target = light.as_ptr();
        for (i, it) in list.iter().enumerate() {
            if it.as_ptr() == target {
                list.del_item(i)?;
                break;
            }
        }
        Ok(())
    }

    fn clear_lights(&self, py: Python<'_>) -> PyResult<()> {
        self.lights.bind(py).call_method0("clear")?;
        Ok(())
    }

    fn set_static(
        &mut self,
        positions: PyArrayLike2<'_, f64, AllowTypeChange>,
        color: [f64; 3],
        intensity: f64,
        radius: f64,
    ) -> PyResult<()> {
        let a = positions.as_array();
        if a.ndim() != 2 || a.shape()[1] != 3 {
            return Err(PyValueError::new_err(
                "static light positions must have shape (N, 3)",
            ));
        }
        self.static_pos = a.rows().into_iter().map(|r| [r[0], r[1], r[2]]).collect();
        self.static_color = color;
        self.static_intensity = intensity;
        self.static_radius = radius;
        Ok(())
    }

    fn clear_static(&mut self) {
        self.static_pos.clear();
    }

    #[getter]
    fn static_count(&self) -> usize {
        self.static_pos.len()
    }

    fn gather(
        &self,
        py: Python<'_>,
        cam: [f64; 3],
    ) -> Vec<(
        [f64; 3],
        (f64, f64, f64),
        f64,
        f64,
        Option<[f64; 3]>,
        Option<f64>,
    )> {
        self.gather_lights(py, cam)
            .into_iter()
            .map(|g| {
                (
                    g.pos,
                    tuple3(g.color),
                    g.intensity,
                    g.radius,
                    g.direction,
                    g.cone,
                )
            })
            .collect()
    }
}

#[pyfunction]
fn lighting_keyframes() -> Vec<f64> {
    KEYS.iter().map(|k| k.0).collect()
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PointLight>()?;
    m.add_class::<Lighting>()?;
    m.add("MAX_LIGHTS", MAX_LIGHTS)?;
    m.add_function(wrap_pyfunction!(lighting_keyframes, m)?)?;
    Ok(())
}
