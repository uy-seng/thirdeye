use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, State};

#[cfg(unix)]
use std::os::unix::process::CommandExt;

const SCREEN_RECORDING_SETTINGS_URL: &str =
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture";
const ISOLATED_DESKTOP_URL: &str = "http://127.0.0.1:3000/";
const MACOS_CAPTURE_HELPER_RESOURCE: &str = "macos_capture/bin/macos_capture_helper";
const MACOS_CAPTURE_HELPER_REPO_RELATIVE_PATH: &str =
    "services/macos-capture-agent/bin/macos_capture_helper";
const PYTHON_SERVICE_DIRS: [&str; 4] = [
    "services/controller-api/src",
    "services/desktop-agent/src",
    "services/macos-capture-agent/src",
    "packages",
];
const CONTROLLER_API_PORT: u16 = 8788;
const MACOS_CAPTURE_PORT: u16 = 8791;
const BUILD_REPO_ROOT: Option<&str> = option_env!("THIRDEYE_REPO_ROOT");

#[derive(Deserialize, Serialize)]
struct CommandResult {
    ok: bool,
    detail: String,
    runtime_root: String,
}

#[derive(Deserialize, Serialize)]
struct ServiceReport {
    name: String,
    running: bool,
    detail: String,
}

#[derive(Deserialize, Serialize)]
struct ServiceStatus {
    runtime_root: String,
    controller_api_url: String,
    reports: Vec<ServiceReport>,
}

#[derive(Default)]
struct AppServiceManager {
    children: Mutex<AppServiceChildren>,
}

#[derive(Default)]
struct AppServiceChildren {
    macos_capture_agent: Option<Child>,
    controller_api: Option<Child>,
}

#[tauri::command]
fn start_services(
    app: AppHandle,
    manager: State<'_, AppServiceManager>,
) -> Result<CommandResult, String> {
    let repo_root = discover_repo_root()?;
    let runtime_root = application_support_root()?;
    ensure_runtime_dirs(&runtime_root)?;
    let helper_bin = macos_capture_helper(&app, &repo_root)?;

    let mut children = manager
        .children
        .lock()
        .map_err(|_| "Unable to lock local service manager.".to_string())?;

    reconcile_macos_capture_agent(&repo_root, &runtime_root, &helper_bin, &mut children)?;
    reconcile_controller_api(&repo_root, &runtime_root, &mut children)?;

    Ok(CommandResult {
        ok: true,
        detail: "Local services are starting.".to_string(),
        runtime_root: runtime_root.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn stop_services(manager: State<'_, AppServiceManager>) -> Result<CommandResult, String> {
    let runtime_root = application_support_root()?;
    let mut children = manager
        .children
        .lock()
        .map_err(|_| "Unable to lock local service manager.".to_string())?;

    stop_child_service(
        &runtime_root,
        "macos-capture-agent",
        &mut children.macos_capture_agent,
    )?;
    stop_child_service(
        &runtime_root,
        "controller-api",
        &mut children.controller_api,
    )?;

    Ok(CommandResult {
        ok: true,
        detail: "Local services started by thirdeye were stopped.".to_string(),
        runtime_root: runtime_root.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn service_status(app: AppHandle) -> Result<ServiceStatus, String> {
    run_supervisor_json(&app, "status")
}

#[tauri::command]
fn open_screen_recording_settings() -> Result<(), String> {
    Command::new("open")
        .arg(SCREEN_RECORDING_SETTINGS_URL)
        .status()
        .map_err(|error| format!("Unable to open capture settings: {error}"))?;
    Ok(())
}

#[tauri::command]
fn open_logs_folder() -> Result<(), String> {
    let logs_dir = application_support_root()?.join("logs");
    fs::create_dir_all(&logs_dir)
        .map_err(|error| format!("Unable to create logs folder: {error}"))?;
    Command::new("open")
        .arg(&logs_dir)
        .status()
        .map_err(|error| format!("Unable to open logs folder: {error}"))?;
    Ok(())
}

#[tauri::command]
fn open_isolated_desktop() -> Result<(), String> {
    Command::new("open")
        .arg(ISOLATED_DESKTOP_URL)
        .status()
        .map_err(|error| format!("Unable to open isolated desktop: {error}"))?;
    Ok(())
}

#[tauri::command]
fn open_artifact_in_finder(path: String) -> Result<(), String> {
    let path = PathBuf::from(path);
    if !path.is_file() {
        return Err("File is not available yet.".to_string());
    }

    let status = Command::new("open")
        .arg("-R")
        .arg(&path)
        .status()
        .map_err(|error| format!("Unable to open file in Finder: {error}"))?;
    if !status.success() {
        return Err("Finder could not open this file.".to_string());
    }
    Ok(())
}

fn reconcile_macos_capture_agent(
    repo_root: &Path,
    runtime_root: &Path,
    helper_bin: &Path,
    children: &mut AppServiceChildren,
) -> Result<(), String> {
    let child_running = child_is_running(&mut children.macos_capture_agent)?;
    let port_open = is_port_open(MACOS_CAPTURE_PORT);
    let active_capture = port_open && macos_capture_has_active_capture();
    let permission_denied = port_open && macos_capture_permission_denied();

    if !child_running && port_open && !active_capture {
        let pid_file = supervisor_pid_file(runtime_root, "macos-capture-agent");
        if permission_denied || pid_file.exists() {
            stop_supervised_service(runtime_root, "macos-capture-agent")?;
            wait_for_port_closed(MACOS_CAPTURE_PORT, Duration::from_secs(3));
        }
    }

    if !is_port_open(MACOS_CAPTURE_PORT) {
        let command = macos_capture_command(repo_root, runtime_root, helper_bin);
        spawn_app_service(
            repo_root,
            runtime_root,
            "macos-capture-agent",
            &command,
            &mut children.macos_capture_agent,
        )?;
        wait_for_port_open(MACOS_CAPTURE_PORT, "This Mac capture", Duration::from_secs(10))?;
    }

    Ok(())
}

fn reconcile_controller_api(
    repo_root: &Path,
    runtime_root: &Path,
    children: &mut AppServiceChildren,
) -> Result<(), String> {
    if child_is_running(&mut children.controller_api)? || is_port_open(CONTROLLER_API_PORT) {
        return Ok(());
    }

    let command = controller_api_command(repo_root, runtime_root);
    spawn_app_service(
        repo_root,
        runtime_root,
        "controller-api",
        &command,
        &mut children.controller_api,
    )?;
    wait_for_port_open(CONTROLLER_API_PORT, "Controller API", Duration::from_secs(10))
}

fn spawn_app_service(
    repo_root: &Path,
    runtime_root: &Path,
    name: &str,
    command_line: &str,
    slot: &mut Option<Child>,
) -> Result<(), String> {
    ensure_runtime_dirs(runtime_root)?;
    let log_path = runtime_root.join("logs").join(format!("{name}.log"));
    let stdout = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|error| format!("Unable to open {name} log: {error}"))?;
    let stderr = stdout
        .try_clone()
        .map_err(|error| format!("Unable to open {name} log: {error}"))?;

    let mut command = Command::new("/bin/bash");
    command
        .arg("-lc")
        .arg(command_line)
        .current_dir(repo_root)
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    #[cfg(unix)]
    command.process_group(0);

    let child = command
        .spawn()
        .map_err(|error| format!("Unable to start {name}: {error}"))?;
    fs::write(
        supervisor_pid_file(runtime_root, name),
        child.id().to_string(),
    )
    .map_err(|error| format!("Unable to write {name} pid file: {error}"))?;
    *slot = Some(child);
    Ok(())
}

fn child_is_running(slot: &mut Option<Child>) -> Result<bool, String> {
    let Some(child) = slot.as_mut() else {
        return Ok(false);
    };
    match child.try_wait() {
        Ok(None) => Ok(true),
        Ok(Some(_)) => {
            *slot = None;
            Ok(false)
        }
        Err(error) => Err(format!("Unable to inspect local service: {error}")),
    }
}

fn stop_child_service(
    runtime_root: &Path,
    name: &str,
    slot: &mut Option<Child>,
) -> Result<(), String> {
    if let Some(mut child) = slot.take() {
        terminate_process_group(child.id(), "TERM");
        if !wait_for_child_exit(&mut child, Duration::from_secs(3)) {
            terminate_process_group(child.id(), "KILL");
            let _ = child.wait();
        }
    }
    stop_supervised_service(runtime_root, name)
}

fn wait_for_child_exit(child: &mut Child, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(_)) => return true,
            Ok(None) => std::thread::sleep(Duration::from_millis(50)),
            Err(_) => return true,
        }
    }
    false
}

fn terminate_process_group(pid: u32, signal: &str) {
    let _ = Command::new("kill")
        .arg(format!("-{signal}"))
        .arg(format!("-{pid}"))
        .status();
}

fn stop_supervised_service(runtime_root: &Path, name: &str) -> Result<(), String> {
    let pid_file = supervisor_pid_file(runtime_root, name);
    if let Some(pid) = read_pid(&pid_file) {
        terminate_process_group(pid, "TERM");
    }
    if pid_file.exists() {
        fs::remove_file(&pid_file)
            .map_err(|error| format!("Unable to remove {name} pid file: {error}"))?;
    }
    Ok(())
}

fn supervisor_pid_file(runtime_root: &Path, name: &str) -> PathBuf {
    runtime_root.join("supervisor").join(format!("{name}.pid"))
}

fn read_pid(path: &Path) -> Option<u32> {
    fs::read_to_string(path).ok()?.trim().parse().ok()
}

fn is_port_open(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&address, Duration::from_millis(250)).is_ok()
}

fn wait_for_port_closed(port: u16, timeout: Duration) {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if !is_port_open(port) {
            return;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

fn wait_for_port_open(port: u16, name: &str, timeout: Duration) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if is_port_open(port) {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    Err(format!(
        "{name} did not start listening on 127.0.0.1:{port}"
    ))
}

fn macos_capture_permission_denied() -> bool {
    match local_http_get(MACOS_CAPTURE_PORT, "/targets", Duration::from_secs(2)) {
        Ok(response) => response.contains("screen_recording_permission_denied"),
        Err(_) => false,
    }
}

fn macos_capture_has_active_capture() -> bool {
    match local_http_get(MACOS_CAPTURE_PORT, "/status", Duration::from_secs(2)) {
        Ok(response) => response.contains("\"running\":true"),
        Err(_) => false,
    }
}

fn local_http_get(port: u16, path: &str, timeout: Duration) -> Result<String, String> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, timeout)
        .map_err(|error| format!("Unable to connect to local service: {error}"))?;
    stream
        .set_read_timeout(Some(timeout))
        .map_err(|error| format!("Unable to configure local service read timeout: {error}"))?;
    stream
        .write_all(
            format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                .as_bytes(),
        )
        .map_err(|error| format!("Unable to query local service: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("Unable to read local service response: {error}"))?;
    Ok(response)
}

fn run_supervisor_json<T: DeserializeOwned>(app: &AppHandle, command: &str) -> Result<T, String> {
    let repo_root = discover_repo_root()?;
    let runtime_root = application_support_root()?;
    let python = repo_root.join(".venv/bin/python");
    let python_bin = if python.exists() {
        python
    } else {
        PathBuf::from("python3")
    };

    let mut process = Command::new(python_bin);
    process
        .arg("-m")
        .arg("core.local_services")
        .arg(command)
        .arg("--repo-root")
        .arg(&repo_root)
        .arg("--runtime-root")
        .arg(&runtime_root)
        .arg("--json")
        .current_dir(&repo_root);
    process.env("PYTHONPATH", service_pythonpath(&repo_root));

    if let Some(helper) = bundled_macos_capture_helper(app) {
        process.env("MACOS_CAPTURE_HELPER_BIN", helper);
    }

    let output = process
        .output()
        .map_err(|error| format!("Unable to run local service supervisor: {error}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        return Err(if stderr.is_empty() { stdout } else { stderr });
    }

    serde_json::from_slice(&output.stdout).map_err(|error| {
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        format!("Unable to read local service supervisor output: {error}: {stdout}")
    })
}

fn macos_capture_helper(app: &AppHandle, repo_root: &Path) -> Result<PathBuf, String> {
    if let Some(helper) = bundled_macos_capture_helper(app) {
        return Ok(helper);
    }
    let helper = repo_root.join(MACOS_CAPTURE_HELPER_REPO_RELATIVE_PATH);
    if helper.exists() {
        return Ok(helper);
    }
    Err(format!(
        "macOS capture helper is missing at {}. Build it with scripts/build_macos_capture_helper.sh.",
        helper.display()
    ))
}

fn bundled_macos_capture_helper(app: &AppHandle) -> Option<PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let bundled_helper = resource_dir.join(MACOS_CAPTURE_HELPER_RESOURCE);
    bundled_helper.exists().then_some(bundled_helper)
}

fn ensure_runtime_dirs(runtime_root: &Path) -> Result<(), String> {
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

fn python_bin(repo_root: &Path) -> PathBuf {
    let python = repo_root.join(".venv/bin/python");
    if python.exists() {
        python
    } else {
        PathBuf::from("python3")
    }
}

fn controller_api_command(repo_root: &Path, runtime_root: &Path) -> String {
    format!(
        "set -a; [ ! -f .env ] || . ./.env; set +a; \
         PYTHONPATH={} \
         CONTROLLER_BASE_URL=http://127.0.0.1:{CONTROLLER_API_PORT} \
         CONTROLLER_CORS_ORIGINS=http://127.0.0.1:1420,tauri://localhost \
         CONTROLLER_DB_PATH={} \
         ARTIFACTS_ROOT={} \
         RECORDINGS_ROOT={} \
         CONTROLLER_EVENTS_ROOT={} \
         MACOS_CAPTURE_BASE_URL=http://127.0.0.1:{MACOS_CAPTURE_PORT} \
         OPENCLAW_BASE_URL=${{LOCAL_OPENCLAW_BASE_URL:-http://127.0.0.1:18789}} \
         {} -m uvicorn api.main:create_app --factory --host 127.0.0.1 --port {CONTROLLER_API_PORT}",
        shell_escape_text(&service_pythonpath(repo_root)),
        shell_escape(&runtime_root.join("controller").join("controller.db")),
        shell_escape(&runtime_root.join("artifacts")),
        shell_escape(&runtime_root.join("recordings")),
        shell_escape(&runtime_root.join("controller-events")),
        shell_escape(&python_bin(repo_root)),
    )
}

fn macos_capture_command(repo_root: &Path, runtime_root: &Path, helper_bin: &Path) -> String {
    format!(
        "set -a; [ ! -f .env ] || . ./.env; set +a; \
         PYTHONPATH={} \
         MACOS_CAPTURE_RUNTIME_DIR={} \
         MACOS_CAPTURE_HELPER_BIN={} \
         PYTHONUNBUFFERED=1 \
         {} -m uvicorn thirdeye_macos_capture.agent.main:app --host 127.0.0.1 --port {MACOS_CAPTURE_PORT}",
        shell_escape_text(&service_pythonpath(repo_root)),
        shell_escape(&runtime_root.join("macos-capture-runtime")),
        shell_escape(helper_bin),
        shell_escape(&python_bin(repo_root)),
    )
}

fn shell_escape(path: &Path) -> String {
    format!("'{}'", path.to_string_lossy().replace('\'', "'\\''"))
}

fn shell_escape_text(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}

fn service_pythonpath(repo_root: &Path) -> String {
    PYTHON_SERVICE_DIRS
        .iter()
        .map(|directory| repo_root.join(directory).to_string_lossy().to_string())
        .collect::<Vec<_>>()
        .join(":")
}

fn application_support_root() -> Result<PathBuf, String> {
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

fn discover_repo_root() -> Result<PathBuf, String> {
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppServiceManager::default())
        .invoke_handler(tauri::generate_handler![
            start_services,
            stop_services,
            service_status,
            open_screen_recording_settings,
            open_logs_folder,
            open_isolated_desktop,
            open_artifact_in_finder
        ])
        .run(tauri::generate_context!())
        .expect("error while running thirdeye");
}
