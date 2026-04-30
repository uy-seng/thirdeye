use crate::runtime::application_support_root;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

const SCREEN_RECORDING_SETTINGS_URL: &str =
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture";
const ISOLATED_DESKTOP_URL: &str = "http://127.0.0.1:3000/";

#[tauri::command]
pub(crate) fn open_screen_recording_settings() -> Result<(), String> {
    Command::new("open")
        .arg(SCREEN_RECORDING_SETTINGS_URL)
        .status()
        .map_err(|error| format!("Unable to open capture settings: {error}"))?;
    Ok(())
}

#[tauri::command]
pub(crate) fn open_logs_folder() -> Result<(), String> {
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
pub(crate) fn open_isolated_desktop() -> Result<(), String> {
    Command::new("open")
        .arg(ISOLATED_DESKTOP_URL)
        .status()
        .map_err(|error| format!("Unable to open isolated desktop: {error}"))?;
    Ok(())
}

#[tauri::command]
pub(crate) fn open_artifact_in_finder(path: String) -> Result<(), String> {
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
