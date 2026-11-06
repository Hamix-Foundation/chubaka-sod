mod canvas;
mod devtools;
mod gpu;
mod keys;
mod lighting;
mod media;
mod mesh;
mod noise;
mod object;
mod particles;
mod platform;
mod renderer;
mod scene;
mod store;
mod window;

#[cfg(all(target_os = "android", feature = "android-host"))]
mod android;

use pyo3::prelude::*;

#[pyfunction]
fn log_line(level: u8, text: &str) {
    if level == 0 {
        log::info!(target: "python", "{text}");
    } else {
        log::error!(target: "python", "{text}");
    }
}

#[pyfunction]
fn rustc_version() -> &'static str {
    env!("LYSYK_RUSTC_VERSION")
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let _ = pyo3_log::try_init();
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    store::register(m)?;
    mesh::register(m)?;
    object::register(m)?;
    scene::register(m)?;
    lighting::register(m)?;
    particles::register(m)?;
    noise::register(m)?;
    canvas::register(m)?;
    renderer::register(m)?;
    media::video::register(m)?;
    window::register(m)?;
    devtools::register(m)?;
    m.add_function(wrap_pyfunction!(log_line, m)?)?;
    m.add_function(wrap_pyfunction!(rustc_version, m)?)?;
    #[cfg(all(target_os = "android", feature = "android-host"))]
    platform::android_audio::register(m)?;
    Ok(())
}

#[cfg(feature = "android-host")]
pub(crate) fn register_builtin() {
    pyo3::append_to_inittab!(_native);
}
