use std::process::Command;

fn main() {
    println!("cargo:rerun-if-env-changed=LYSYK_RUSTC_VERSION");
    let version = std::env::var("LYSYK_RUSTC_VERSION").ok().filter(|value| !value.is_empty()).unwrap_or_else(|| {
        Command::new(std::env::var("RUSTC").unwrap_or_else(|_| "rustc".to_string()))
            .arg("--version")
            .output()
            .ok()
            .filter(|output| output.status.success())
            .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_string())
            .unwrap_or_else(|| "unknown".to_string())
    });
    println!("cargo:rustc-env=LYSYK_RUSTC_VERSION={version}");
}
