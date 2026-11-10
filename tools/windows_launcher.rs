#![windows_subsystem = "windows"]

use std::env;
use std::process::Command;
use std::os::windows::process::CommandExt;

fn main() {
    let Ok(exe) = env::current_exe() else { return };
    let Some(root) = exe.parent() else { return };
    let python = root.join("runtime").join("python.exe");
    let game = root.join("game").join("run.py");
    let mut command = Command::new(python);
    command.arg(game).args(env::args_os().skip(1)).current_dir(root);
    // Keep Python's diagnostics visible in a console window when the game fails.
    command.creation_flags(0x00000010);
    if let Ok(mut child) = command.spawn() {
        let _ = child.wait();
    }
}
