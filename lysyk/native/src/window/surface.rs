#[pyclass(unsendable, module = "lysyk.engine._native")]
pub struct WindowCore {
    shared: Arc<Shared>,
    event_loop: Option<EventLoop<()>>,
    handle: Py<GpuHandle>,
}

#[cfg(all(target_os = "android", feature = "android-host"))]
fn make_event_loop() -> Result<EventLoop<()>, String> {
    use winit::platform::android::EventLoopBuilderExtAndroid;
    let app =
        crate::android::app().ok_or_else(|| "the Android app handle is not set".to_string())?;
    EventLoop::builder()
        .with_android_app(app)
        .build()
        .map_err(|e| e.to_string())
}

#[cfg(not(all(target_os = "android", feature = "android-host")))]
fn make_event_loop() -> Result<EventLoop<()>, String> {
    EventLoop::new().map_err(|e| e.to_string())
}

struct SendBox<T>(T);
unsafe impl<T> Send for SendBox<T> {}

#[pymethods]
impl WindowCore {
    #[new]
    #[pyo3(signature = (width, height, title, resizable=true, vsync=true, msaa=true, api="auto", fonts_dir=""))]
    #[allow(deprecated)]
    fn new(
        py: Python<'_>,
        width: u32,
        height: u32,
        title: &str,
        resizable: bool,
        vsync: bool,
        msaa: bool,
        api: &str,
        fonts_dir: &str,
    ) -> PyResult<Self> {
        let api = Api::parse(&std::env::var("LYSYK_BACKEND").unwrap_or_else(|_| api.to_string()))?;
        let event_loop = make_event_loop().map_err(|e| {
            PyRuntimeError::new_err(format!("cannot create the event loop (no display?): {e}"))
        })?;
        let attrs = WindowAttributes::default()
            .with_title(title)
            .with_resizable(resizable)
            .with_inner_size(LogicalSize::new(width as f64, height as f64));
        let window: Option<Arc<Window>> = if cfg!(target_os = "android") {
            None
        } else {
            Some(Arc::new(
                event_loop
                    .create_window(attrs)
                    .map_err(|e| PyRuntimeError::new_err(e.to_string()))?,
            ))
        };
        let display_handle = event_loop.owned_display_handle();
        let display = move || {
            Some(Box::new(display_handle.clone()) as Box<dyn wgpu::wgt::WgpuHasDisplayHandle>)
        };
        let (pw, ph, ratio) = match &window {
            Some(w) => {
                let s = w.inner_size();
                (s.width.max(1), s.height.max(1), w.scale_factor())
            }
            None => (width, height, 1.0),
        };
        let wclone = window.clone();
        let make_surface = move |inst: &wgpu::Instance| -> Option<wgpu::Surface<'static>> {
            wclone
                .as_ref()
                .and_then(|w| inst.create_surface(w.clone()).ok())
        };
        let opened = py.detach(|| open(api, msaa, pw, ph, &display, Some(&make_surface)))?;
        let gpu = opened.gpu;
        if let Some(s) = &opened.surface {
            gpu.configure_surface(s, pw, ph, vsync);
        }
        let fonts = PathBuf::from(fonts_dir);
        let canvas = Py::new(py, Canvas::new_inner(gpu.clone(), &fonts))?;
        let shared = Arc::new(Shared {
            gpu: gpu.clone(),
            window: Mutex::new(window),
            inner: Mutex::new(Inner {
                surface: opened.surface,
                vsync,
                frame_interval: 0.0,
                fullscreen: false,
                windowed_rect: None,
                width: pw,
                height: ph,
                pixel_ratio: ratio,
                mouse: (0.0, 0.0),
                title: title.to_string(),
                fps: 0.0,
                frame_ms: 0.0,
                overlay: std::env::var("LYSYK_OVERLAY").map_or(false, |v| v == "1"),
                mods: 0,
                touch: None,
                emulate_touch: true,
                touch_seen: false,
            }),
            canvas,
        });
        let handle = Py::new(py, GpuHandle { gpu })?;
        Ok(WindowCore {
            shared,
            event_loop: Some(event_loop),
            handle,
        })
    }

    #[getter]
    fn gpu(&self, py: Python<'_>) -> Py<GpuHandle> {
        self.handle.clone_ref(py)
    }

    #[getter]
    fn canvas(&self, py: Python<'_>) -> Py<Canvas> {
        self.shared.canvas.clone_ref(py)
    }

    #[getter]
    fn width(&self) -> u32 {
        self.shared.inner.lock().unwrap().width
    }

    #[getter]
    fn height(&self) -> u32 {
        self.shared.inner.lock().unwrap().height
    }

    #[getter]
    fn pixel_ratio(&self) -> f64 {
        self.shared.inner.lock().unwrap().pixel_ratio
    }

    #[getter]
    fn mouse_x(&self) -> f64 {
        self.shared.inner.lock().unwrap().mouse.0
    }

    #[getter]
    fn mouse_y(&self) -> f64 {
        self.shared.inner.lock().unwrap().mouse.1
    }

    #[getter]
    fn fps(&self) -> f64 {
        self.shared.inner.lock().unwrap().fps
    }

    #[getter]
    fn frame_time_ms(&self) -> f64 {
        self.shared.inner.lock().unwrap().frame_ms
    }

    #[getter]
    fn fullscreen(&self) -> bool {
        self.shared.inner.lock().unwrap().fullscreen
    }

    #[getter]
    fn title(&self) -> String {
        self.shared.inner.lock().unwrap().title.clone()
    }

    #[getter]
    fn overlay(&self) -> bool {
        self.shared.inner.lock().unwrap().overlay
    }

    #[setter]
    fn set_overlay(&self, v: bool) {
        self.shared.inner.lock().unwrap().overlay = v;
    }

    fn set_title(&self, title: &str) {
        self.shared.inner.lock().unwrap().title = title.to_string();
        if let Some(w) = self.shared.window.lock().unwrap().as_ref() {
            w.set_title(title);
        }
    }

    fn set_vsync(&self, enabled: bool) {
        let mut i = self.shared.inner.lock().unwrap();
        if i.vsync == enabled {
            return;
        }
        i.vsync = enabled;
        if let Some(s) = &i.surface {
            self.shared
                .gpu
                .configure_surface(s, i.width, i.height, enabled);
        }
    }

    fn set_fps_limit(&self, fps: f64) {
        self.shared.inner.lock().unwrap().frame_interval = if fps > 0.0 { 1.0 / fps } else { 0.0 };
    }

    fn set_msaa(&self, enabled: bool) {
        self.shared.gpu.set_msaa(enabled);
    }

    fn set_render_scale(&self, scale: f32) {
        self.shared.gpu.set_render_scale(scale);
    }

    fn msaa_samples(&self) -> u32 {
        self.shared.gpu.state.lock().unwrap().sample_count
    }

    fn clear(&self, color: (f64, f64, f64)) {
        self.shared.gpu.state.lock().unwrap().clear = [
            (color.0 / 255.0) as f32,
            (color.1 / 255.0) as f32,
            (color.2 / 255.0) as f32,
        ];
    }

    fn set_fullscreen(&self, enabled: bool) {
        let mut i = self.shared.inner.lock().unwrap();
        if i.fullscreen == enabled {
            return;
        }
        let guard = self.shared.window.lock().unwrap();
        let Some(w) = guard.as_ref() else { return };
        if enabled {
            let pos = w
                .outer_position()
                .unwrap_or(PhysicalPosition::new(100, 100));
            let size = w.inner_size();
            i.windowed_rect = Some((pos.x, pos.y, size.width, size.height));
            w.set_fullscreen(Some(Fullscreen::Borderless(None)));
        } else {
            w.set_fullscreen(None);
        }
        i.fullscreen = enabled;
    }

    fn monitor_info<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyDict>>> {
        let guard = self.shared.window.lock().unwrap();
        let Some(m) = guard
            .as_ref()
            .and_then(|w| w.current_monitor().or_else(|| w.primary_monitor()))
        else {
            return Ok(None);
        };
        let d = PyDict::new(py);
        d.set_item("name", m.name().unwrap_or_default())?;
        d.set_item("width", m.size().width)?;
        d.set_item("height", m.size().height)?;
        d.set_item(
            "refresh",
            m.refresh_rate_millihertz()
                .map_or(0, |r| (r as f64 / 1000.0).round() as u32),
        )?;
        Ok(Some(d))
    }

    fn set_cursor_visible(&self, visible: bool) {
        let guard = self.shared.window.lock().unwrap();
        if let Some(w) = guard.as_ref() {
            w.set_cursor_visible(visible);
        }
    }

    fn set_cursor_grab(&self, mode: &str) -> bool {
        use winit::window::CursorGrabMode;
        let guard = self.shared.window.lock().unwrap();
        let Some(w) = guard.as_ref() else {
            return false;
        };
        match mode {
            "confined" => w.set_cursor_grab(CursorGrabMode::Confined).is_ok(),
            "locked" => {
                w.set_cursor_grab(CursorGrabMode::Locked).is_ok()
                    || w.set_cursor_grab(CursorGrabMode::Confined).is_ok()
            }
            _ => w.set_cursor_grab(CursorGrabMode::None).is_ok(),
        }
    }

    #[getter]
    fn is_mobile(&self) -> bool {
        cfg!(target_os = "android") || self.shared.inner.lock().unwrap().touch_seen
    }

    #[getter]
    fn touch_emulates_mouse(&self) -> bool {
        self.shared.inner.lock().unwrap().emulate_touch
    }

    #[setter]
    fn set_touch_emulates_mouse(&self, v: bool) {
        self.shared.inner.lock().unwrap().emulate_touch = v;
    }

    fn center_window(&self) {
        let guard = self.shared.window.lock().unwrap();
        let Some(w) = guard.as_ref() else { return };
        if let Some(m) = w.current_monitor().or_else(|| w.primary_monitor()) {
            let (ms, mp, ws) = (m.size(), m.position(), w.outer_size());
            w.set_outer_position(PhysicalPosition::new(
                mp.x + (ms.width as i32 - ws.width as i32) / 2,
                mp.y + (ms.height as i32 - ws.height as i32) / 2,
            ));
        }
    }

    fn close(&self) {
        CLOSE.with(|c| c.set(true));
    }

    fn set_clipboard(&self, text: &str) {
        #[cfg(not(target_os = "android"))]
        CLIP.with(|c| {
            let mut c = c.borrow_mut();
            if c.is_none() {
                *c = arboard::Clipboard::new().ok();
            }
            if let Some(cb) = c.as_mut() {
                let _ = cb.set_text(text.to_string());
            }
        });
        let _ = text;
    }

    fn screenshot(&self, path: &str) {
        *self.shared.gpu.screenshot.lock().unwrap() = Some(path.to_string());
    }

    fn run(slf: &Bound<'_, Self>, py: Python<'_>, handler: Py<PyAny>) -> PyResult<()> {
        let (shared, event_loop) = {
            let mut me = slf.borrow_mut();
            let el = me
                .event_loop
                .take()
                .ok_or_else(|| PyRuntimeError::new_err("run() was already called"))?;
            (me.shared.clone(), el)
        };
        CLOSE.with(|c| c.set(false));
        let mut app = App {
            shared: shared.clone(),
            handler: handler.clone_ref(py),
            error: None,
            last: Instant::now(),
            fps_t: Instant::now(),
            fps_n: 0,
            started: false,
        };
        let pack = SendBox((event_loop, &mut app));
        let result = py.detach(move || {
            let pack = pack;
            let (el, app) = pack.0;
            el.run_app(app)
        });
        if let Some(e) = app.error.take() {
            return Err(e);
        }
        result.map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        handler.bind(py).call_method0("on_close")?;
        Ok(())
    }
}

thread_local! {
    static CLOSE: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

struct App {
    shared: Arc<Shared>,
    handler: Py<PyAny>,
    error: Option<PyErr>,
    last: Instant,
    fps_t: Instant,
    fps_n: u32,
    started: bool,
}

impl App {
    fn call(
        &mut self,
        el: &ActiveEventLoop,
        py: Python<'_>,
        name: &str,
        args: impl for<'a> pyo3::call::PyCallArgs<'a>,
    ) {
        if self.error.is_some() {
            return;
        }
        if let Err(e) = self.handler.bind(py).call_method1(name, args) {
            self.error = Some(e);
            el.exit();
        }
    }

    fn ensure_surface(&mut self) {
        let window = self.shared.window.lock().unwrap().clone();
        let Some(w) = window else { return };
        let mut i = self.shared.inner.lock().unwrap();
        if i.surface.is_none() {
            if let Ok(s) = self.shared.gpu.instance.create_surface(w.clone()) {
                let size = w.inner_size();
                i.width = size.width.max(1);
                i.height = size.height.max(1);
                self.shared
                    .gpu
                    .configure_surface(&s, i.width, i.height, i.vsync);
                i.surface = Some(s);
            }
        }
    }

    fn frame(&mut self, el: &ActiveEventLoop) {
        let shared = self.shared.clone();
        let gpu = shared.gpu.clone();
        let (w, h) = {
            let i = shared.inner.lock().unwrap();
            (i.width, i.height)
        };
        if w == 0 || h == 0 {
            return;
        }
        let tex = {
            let i = shared.inner.lock().unwrap();
            let Some(s) = i.surface.as_ref() else { return };
            let mut tm = Timer::start();
            let r = s.get_current_texture();
            let waited = tm.lap();
            drop(i);
            match r {
                wgpu::CurrentSurfaceTexture::Success(t)
                | wgpu::CurrentSurfaceTexture::Suboptimal(t) => Some((t, waited)),
                wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                    let i = shared.inner.lock().unwrap();
                    let (iw, ih, v) = (i.width, i.height, i.vsync);
                    if let Some(s) = i.surface.as_ref() {
                        gpu.configure_surface(s, iw, ih, v);
                    }
                    None
                }
                _ => None,
            }
        };
        let Some((frame, waited)) = tex else { return };
        let started = Instant::now();
        let present_wait = std::cell::Cell::new(waited);
        let shot;
        let readback;
        let mut offscreen: Option<wgpu::Texture> = None;
        {
            let out = Python::attach(|py| {
                gpu.profiler.begin();
                let now = Instant::now();
                let dt = (now - self.last).as_secs_f64().min(0.1);
                self.last = now;
                shared.canvas.bind(py).borrow_mut().dt = dt;
                let mut timer = Timer::start();
                self.call(el, py, "on_update", (dt,));
                gpu.profiler.add(0, timer.lap());
                let pending = gpu.screenshot.lock().unwrap().take();
                let can_copy = frame
                    .texture
                    .usage()
                    .contains(wgpu::TextureUsages::COPY_SRC);
                let fmt = gpu.state.lock().unwrap().format;
                if pending.is_some() && !can_copy {
                    offscreen = Some(gpu.device.create_texture(&wgpu::TextureDescriptor {
                        label: Some("screenshot target"),
                        size: wgpu::Extent3d {
                            width: w,
                            height: h,
                            depth_or_array_layers: 1,
                        },
                        mip_level_count: 1,
                        sample_count: 1,
                        dimension: wgpu::TextureDimension::D2,
                        format: fmt,
                        usage: wgpu::TextureUsages::RENDER_ATTACHMENT
                            | wgpu::TextureUsages::COPY_SRC,
                        view_formats: &[],
                    }));
                }
                let target_tex = offscreen.as_ref().unwrap_or(&frame.texture);
                let view = target_tex.create_view(&wgpu::TextureViewDescriptor::default());
                begin_frame(py, &gpu, &shared.canvas, view);
                let mut t2 = Timer::start();
                self.call(el, py, "on_draw", ());
                gpu.profiler.add(1, t2.lap());
                let (overlay, fps) = {
                    let i = shared.inner.lock().unwrap();
                    (i.overlay, i.fps)
                };
                let fin = end_frame(
                    py,
                    &gpu,
                    &shared.canvas,
                    w,
                    h,
                    if overlay { Some(fps) } else { None },
                    if pending.is_some() {
                        Some(target_tex)
                    } else {
                        None
                    },
                );
                (pending, fin)
            });
            shot = out.0;
            readback = out.1.readback;
        }
        let mut tp = Timer::start();
        if offscreen.is_some() {
            drop(frame);
        } else {
            gpu.queue.present(frame);
        }
        present_wait.set(present_wait.get() + tp.lap());
        gpu.profiler.add(8, present_wait.get());
        gpu.profiler.end();
        if let (Some(path), Some((buf, bpr))) = (shot, readback) {
            let fmt = gpu.state.lock().unwrap().format;
            match finish_readback(&gpu, &buf, bpr, w, h, is_bgra(fmt))
                .and_then(|rb| write_png(&path, rb.width, rb.height, &rb.rgba))
            {
                Ok(()) => {
                    log::info!("screenshot saved to {path}");
                    *gpu.dev_message.lock().unwrap() = None;
                }
                Err(e) => log::error!("screenshot failed: {e}"),
            }
        }
        self.fps_n += 1;
        let el_t = self.fps_t.elapsed().as_secs_f64();
        let frame_ms = started.elapsed().as_secs_f64() * 1000.0;
        let interval = {
            let mut i = shared.inner.lock().unwrap();
            i.frame_ms = frame_ms;
            if el_t >= 0.5 {
                i.fps = self.fps_n as f64 / el_t;
                self.fps_n = 0;
                self.fps_t = Instant::now();
            }
            if i.vsync {
                0.0
            } else {
                i.frame_interval
            }
        };
        if interval > 0.0 {
            let target = started + Duration::from_secs_f64(interval);
            let now = Instant::now();
            if target > now + Duration::from_micros(1500) {
                std::thread::sleep(target - now - Duration::from_micros(1000));
            }
            while Instant::now() < target {
                std::thread::yield_now();
            }
        }
    }
}

impl ApplicationHandler for App {
    fn resumed(&mut self, el: &ActiveEventLoop) {
        #[allow(deprecated)]
        {
            let mut guard = self.shared.window.lock().unwrap();
            if guard.is_none() {
                let attrs = WindowAttributes::default()
                    .with_title(self.shared.inner.lock().unwrap().title.clone());
                match el.create_window(attrs) {
                    Ok(w) => *guard = Some(Arc::new(w)),
                    Err(e) => log::error!("cannot create window: {e}"),
                }
            }
        }
        self.ensure_surface();
        if let Some(w) = self.shared.window.lock().unwrap().as_ref() {
            w.request_redraw();
        }
        let (w, h) = {
            let i = self.shared.inner.lock().unwrap();
            (i.width, i.height)
        };
        if !self.started {
            self.started = true;
            self.last = Instant::now();
        } else {
            self.last = Instant::now();
            Python::attach(|py| {
                self.call(el, py, "on_resize", (w, h));
                self.call(el, py, "on_resume", ());
            });
        }
    }

    fn suspended(&mut self, el: &ActiveEventLoop) {
        #[cfg(target_os = "android")]
        {
            self.shared.inner.lock().unwrap().surface = None;
            *self.shared.window.lock().unwrap() = None;
        }
        Python::attach(|py| self.call(el, py, "on_suspend", ()));
    }

    fn window_event(&mut self, el: &ActiveEventLoop, _id: WindowId, event: WindowEvent) {
        if CLOSE.with(|c| c.get()) {
            el.exit();
            return;
        }
        match event {
            WindowEvent::CloseRequested => el.exit(),
            WindowEvent::Resized(size) => {
                let (w, h) = (size.width, size.height);
                {
                    let mut i = self.shared.inner.lock().unwrap();
                    i.width = w;
                    i.height = h;
                    if w > 0 && h > 0 {
                        if let Some(s) = i.surface.as_ref() {
                            self.shared.gpu.configure_surface(s, w, h, i.vsync);
                        }
                    }
                }
                if w > 0 && h > 0 {
                    Python::attach(|py| self.call(el, py, "on_resize", (w, h)));
                }
            }
            WindowEvent::ScaleFactorChanged { scale_factor, .. } => {
                self.shared.inner.lock().unwrap().pixel_ratio = scale_factor;
            }
            WindowEvent::ModifiersChanged(m) => {
                let s = m.state();
                let mut v = 0;
                if s.shift_key() {
                    v |= 1;
                }
                if s.control_key() {
                    v |= 2;
                }
                if s.alt_key() {
                    v |= 4;
                }
                if s.super_key() {
                    v |= 8;
                }
                self.shared.inner.lock().unwrap().mods = v;
            }
            WindowEvent::KeyboardInput { event, .. } => {
                let PhysicalKey::Code(code) = event.physical_key else {
                    return;
                };
                let Some(key) = glfw_code(code) else { return };
                let mods = self.shared.inner.lock().unwrap().mods;
                if event.state == ElementState::Pressed {
                    if !event.repeat {
                        if code == KeyCode::F3 {
                            let mut i = self.shared.inner.lock().unwrap();
                            i.overlay = !i.overlay;
                            return;
                        }
                        if code == KeyCode::F12 {
                            let stamp = std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .map_or(0, |d| d.as_secs());
                            *self.shared.gpu.screenshot.lock().unwrap() =
                                Some(format!("lysyk_{stamp}.png"));
                            return;
                        }
                    }
                    let repeatable = matches!(
                        code,
                        KeyCode::ArrowUp
                            | KeyCode::ArrowDown
                            | KeyCode::ArrowLeft
                            | KeyCode::ArrowRight
                    );
                    if !event.repeat || repeatable {
                        Python::attach(|py| self.call(el, py, "on_key_press", (key, mods)));
                    }
                } else {
                    Python::attach(|py| self.call(el, py, "on_key_release", (key, mods)));
                }
            }
            WindowEvent::CursorMoved { position, .. } => {
                self.shared.inner.lock().unwrap().mouse = (position.x, position.y);
                Python::attach(|py| self.call(el, py, "on_mouse_motion", (position.x, position.y)));
            }
            WindowEvent::MouseInput { state, button, .. } => {
                let b = match button {
                    MouseButton::Left => 0,
                    MouseButton::Right => 1,
                    MouseButton::Middle => 2,
                    _ => return,
                };
                let (x, y) = self.shared.inner.lock().unwrap().mouse;
                let name = if state == ElementState::Pressed {
                    "on_mouse_press"
                } else {
                    "on_mouse_release"
                };
                Python::attach(|py| self.call(el, py, name, (x, y, b)));
            }
            WindowEvent::MouseWheel { delta, .. } => {
                let (dx, dy) = match delta {
                    MouseScrollDelta::LineDelta(x, y) => (x as f64, y as f64),
                    MouseScrollDelta::PixelDelta(p) => (p.x / 40.0, p.y / 40.0),
                };
                Python::attach(|py| self.call(el, py, "on_scroll", (dx, dy)));
            }
            WindowEvent::Touch(t) => {
                let (x, y) = (t.location.x, t.location.y);
                let phase = match t.phase {
                    TouchPhase::Started => "down",
                    TouchPhase::Moved => "move",
                    TouchPhase::Ended => "up",
                    TouchPhase::Cancelled => "cancel",
                };
                let emulate = {
                    let mut i = self.shared.inner.lock().unwrap();
                    i.touch_seen = true;
                    i.emulate_touch
                };
                Python::attach(|py| self.call(el, py, "on_touch", (t.id, phase, x, y)));
                if !emulate {
                    return;
                }
                let mut i = self.shared.inner.lock().unwrap();
                match t.phase {
                    TouchPhase::Started if i.touch.is_none() => {
                        i.touch = Some(t.id);
                        i.mouse = (x, y);
                        drop(i);
                        Python::attach(|py| {
                            self.call(el, py, "on_mouse_motion", (x, y));
                            self.call(el, py, "on_mouse_press", (x, y, 0));
                        });
                    }
                    TouchPhase::Moved if i.touch == Some(t.id) => {
                        i.mouse = (x, y);
                        drop(i);
                        Python::attach(|py| self.call(el, py, "on_mouse_motion", (x, y)));
                    }
                    TouchPhase::Ended | TouchPhase::Cancelled if i.touch == Some(t.id) => {
                        i.touch = None;
                        i.mouse = (x, y);
                        drop(i);
                        Python::attach(|py| self.call(el, py, "on_mouse_release", (x, y, 0)));
                    }
                    _ => {}
                }
            }
            WindowEvent::RedrawRequested => {
                self.frame(el);
                if let Some(w) = self.shared.window.lock().unwrap().as_ref() {
                    w.request_redraw();
                }
            }
            _ => {}
        }
    }

    fn about_to_wait(&mut self, el: &ActiveEventLoop) {
        if self.error.is_some() || CLOSE.with(|c| c.get()) {
            el.exit();
            return;
        }
        if cfg!(target_os = "android") && self.shared.inner.lock().unwrap().surface.is_none() {
            return;
        }
        if let Some(w) = self.shared.window.lock().unwrap().as_ref() {
            w.request_redraw();
        }
    }
}
