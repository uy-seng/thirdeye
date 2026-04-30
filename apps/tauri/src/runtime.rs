use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const PYTHON_SERVICE_DIRS: [&str; 4] = [
    "services/controller-api/src",
    "services/desktop-agent/src",
    "services/macos-capture-agent/src",
    "packages",
];
const BUILD_REPO_ROOT: Option<&str> = option_env!("THIRDEYE_REPO_ROOT");

pub(crate) fn ensure_runtime_dirs(runtime_root: &Path) -> Result<(), String> {
    for directory in [
        runtime_root.join("controller"),
        runtime_root.join("controller-events"),
        runtime_root.join("artifacts"),
        runtime_root.join("recordings"),
        runtime_root.join("logs"),
        runtime_root.join("macos-capture-runtime"),
        runtime_root.join("supervisor"),
    ] {
        fs::create_dir_all(&directory)
            .map_err(|error| format!("Unable to create {}: {error}", directory.display()))?;
    }
    Ok(())
}

pub(crate) fn python_bin(repo_root: &Path) -> PathBuf {
    let python = repo_root.join(".venv/bin/python");
    if python.exists() {
        python
    } else {
        PathBuf::from("python3")
    }
}

pub(crate) fn shell_escape(path: &Path) -> String {
    format!("'{}'", path.to_string_lossy().replace('\'', "'\\''"))
}

pub(crate) fn shell_escape_text(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}

pub(crate) fn service_pythonpath(repo_root: &Path) -> String {
    PYTHON_SERVICE_DIRS
        .iter()
        .map(|directory| repo_root.join(directory).to_string_lossy().to_string())
        .collect::<Vec<_>>()
        .join(":")
}

pub(crate) fn application_support_root() -> Result<PathBuf, String> {
    if let Ok(path) = env::var("THIRDEYE_RUNTIME_ROOT") {
        if !path.trim().is_empty() {
            return Ok(PathBuf::from(path));
        }
    }
    let home = env::var("HOME").map_err(|_| "HOME is not set".to_string())?;
    Ok(PathBuf::from(home)
        .join("Library")
        .join("Application Support")
        .join("thirdeye"))
}

pub(crate) fn discover_repo_root() -> Result<PathBuf, String> {
    if let Ok(path) = env::var("THIRDEYE_REPO_ROOT") {
        let candidate = PathBuf::from(path);
        if is_repo_root(&candidate) {
            return Ok(candidate);
        }
    }

    if let Some(path) = BUILD_REPO_ROOT {
        let candidate = PathBuf::from(path);
        if is_repo_root(&candidate) {
            return Ok(candidate);
        }
    }

    let current_dir =
        env::current_dir().map_err(|error| format!("Unable to read current directory: {error}"))?;
    if let Some(root) = find_repo_root_from(&current_dir) {
        return Ok(root);
    }

    let current_exe =
        env::current_exe().map_err(|error| format!("Unable to read app path: {error}"))?;
    if let Some(parent) = current_exe.parent() {
        if let Some(root) = find_repo_root_from(parent) {
            return Ok(root);
        }
    }

    Err("Set THIRDEYE_REPO_ROOT to the repository folder before starting services.".to_string())
}

fn find_repo_root_from(start: &Path) -> Option<PathBuf> {
    for ancestor in start.ancestors() {
        if is_repo_root(ancestor) {
            return Some(ancestor.to_path_buf());
        }
    }
    None
}

fn is_repo_root(path: &Path) -> bool {
    path.join("Makefile").exists() && path.join("infra/compose.yaml").exists()
}
