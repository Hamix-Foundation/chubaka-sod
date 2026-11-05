use std::ffi::CString;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use pyo3::prelude::*;
use winit::platform::android::activity::AndroidApp;

static APP: OnceLock<AndroidApp> = OnceLock::new();

const BUNDLE: &str = "bundle.tar";
const BOOT: &str = include_str!("android_boot.py");

pub fn app() -> Option<AndroidApp> {
    APP.get().cloned()
}

fn fingerprint(data: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in data {
        h ^= *b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h ^ data.len() as u64
}

fn read_bundle(app: &AndroidApp) -> io::Result<Vec<u8>> {
    let name = CString::new(BUNDLE).unwrap();
    let mut asset = app
        .asset_manager()
        .open(&name)
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "bundle.tar is missing from the APK assets"))?;
    let mut data = Vec::new();
    asset.read_to_end(&mut data)?;
    Ok(data)
}

fn field(block: &[u8], from: usize, to: usize) -> &[u8] {
    let raw = &block[from..to];
    let end = raw.iter().position(|b| *b == 0).unwrap_or(raw.len());
    &raw[..end]
}

fn octal(bytes: &[u8]) -> usize {
    let text = String::from_utf8_lossy(bytes);
    usize::from_str_radix(text.trim().trim_matches('\0'), 8).unwrap_or(0)
}

fn safe_join(root: &Path, name: &str) -> Option<PathBuf> {
    let mut out = root.to_path_buf();
    for part in name.split('/') {
        match part {
            "" | "." => {}
            ".." => return None,
            p => out.push(p),
        }
    }
    Some(out)
}

fn extract(data: &[u8], root: &Path) -> io::Result<()> {
    let mut pos = 0usize;
    let mut long_name: Option<String> = None;
    while pos + 512 <= data.len() {
        let block = &data[pos..pos + 512];
        if block.iter().all(|b| *b == 0) {
            break;
        }
        let size = octal(field(block, 124, 136));
        let kind = block[156];
        let body_start = pos + 512;
        let body_end = body_start + size;
        if body_end > data.len() {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "truncated bundle"));
        }
        let mut name = String::from_utf8_lossy(field(block, 0, 100)).to_string();
        let prefix = String::from_utf8_lossy(field(block, 345, 500)).to_string();
        if !prefix.is_empty() {
            name = format!("{prefix}/{name}");
        }
        if kind == b'L' {
            long_name = Some(String::from_utf8_lossy(field(&data[body_start..body_end], 0, size)).to_string());
        } else {
            let name = long_name.take().unwrap_or(name);
            if let Some(path) = safe_join(root, &name) {
                match kind {
                    b'5' => fs::create_dir_all(&path)?,
                    b'0' | 0 => {
                        if let Some(parent) = path.parent() {
                            fs::create_dir_all(parent)?;
                        }
                        fs::write(&path, &data[body_start..body_end])?;
                    }
                    _ => {}
                }
            }
        }
        pos = body_start + size.div_ceil(512) * 512;
    }
    Ok(())
}

fn prepare(app: &AndroidApp, root: &Path) -> io::Result<()> {
    let data = read_bundle(app)?;
    let stamp = root.join("bundle.stamp");
    let current = fingerprint(&data).to_string();
    let ready = root.join("py").is_dir() && fs::read_to_string(&stamp).map(|s| s == current).unwrap_or(false);
    if ready {
        return Ok(());
    }
    for dir in ["py", "app"] {
        let p = root.join(dir);
        if p.exists() {
            fs::remove_dir_all(&p)?;
        }
    }
    extract(&data, root)?;
    fs::write(&stamp, current)
}

#[no_mangle]
fn android_main(app: AndroidApp) {
    android_logger::init_once(android_logger::Config::default().with_max_level(log::LevelFilter::Info).with_tag("lysyk"));
    let Some(root) = app.internal_data_path() else {
        log::error!("no internal data path");
        return;
    };
    if let Err(e) = prepare(&app, &root) {
        log::error!("cannot prepare the game bundle: {e}");
        return;
    }
    std::env::set_var("PYTHONHOME", root.join("py"));
    std::env::set_var("PYTHONDONTWRITEBYTECODE", "1");
    std::env::set_var("PYTHONUNBUFFERED", "1");
    std::env::set_var("HOME", &root);
    std::env::set_var("XDG_DATA_HOME", root.join("data"));
    std::env::set_var("LYSYK_ROOT", &root);
    if APP.set(app).is_err() {
        return;
    }
    crate::register_builtin();
    let code = CString::new(BOOT).unwrap();
    Python::attach(|py| {
        if let Err(e) = py.run(code.as_c_str(), None, None) {
            log::error!(target: "python", "Android Python startup failed: {e}");
            e.print(py);
        }
    });
}
