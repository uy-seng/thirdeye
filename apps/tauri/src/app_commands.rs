use crate::runtime::application_support_root;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

const SCREEN_RECORDING_SETTINGS_URL: &str =
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture";
const MICROPHONE_SETTINGS_URL: &str =
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone";

#[cfg(target_os = "macos")]
mod macos_microphone {
    use block2::RcBlock;
    use objc2::runtime::{AnyObject, Bool};
    use objc2::{class, msg_send};
    use std::sync::mpsc;
    use std::time::Duration;

    const AUTHORIZATION_NOT_DETERMINED: isize = 0;
    const AUTHORIZATION_RESTRICTED: isize = 1;
    const AUTHORIZATION_DENIED: isize = 2;
    const AUTHORIZATION_AUTHORIZED: isize = 3;

    #[link(name = "AVFoundation", kind = "framework")]
    extern "C" {
        #[link_name = "AVMediaTypeAudio"]
        static AV_MEDIA_TYPE_AUDIO: *const AnyObject;
    }

    pub(super) fn request_access() -> Result<bool, String> {
        let media_type = unsafe { AV_MEDIA_TYPE_AUDIO };
        if media_type.is_null() {
            return Err("Microphone access is not available on this Mac.".to_string());
        }

        let status: isize = unsafe {
            msg_send![
                class!(AVCaptureDevice),
                authorizationStatusForMediaType: media_type
            ]
        };
        match status {
            AUTHORIZATION_AUTHORIZED => Ok(true),
            AUTHORIZATION_DENIED | AUTHORIZATION_RESTRICTED => Ok(false),
            AUTHORIZATION_NOT_DETERMINED => request_access_prompt(media_type),
            _ => Ok(false),
        }
    }

    fn request_access_prompt(media_type: *const AnyObject) -> Result<bool, String> {
        let (sender, receiver) = mpsc::channel();
        let completion = RcBlock::new(move |granted: Bool| {
            let _ = sender.send(granted.as_bool());
        });

        let _: () = unsafe {
            msg_send![
                class!(AVCaptureDevice),
                requestAccessForMediaType: media_type,
                completionHandler: &*completion
            ]
        };

        receiver
            .recv_timeout(Duration::from_secs(120))
            .map_err(|_| "Timed out waiting for microphone access.".to_string())
    }
}

#[cfg(not(target_os = "macos"))]
mod macos_microphone {
    pub(super) fn request_access() -> Result<bool, String> {
        Ok(true)
    }
}

#[tauri::command]
pub(crate) fn open_screen_recording_settings() -> Result<(), String> {
    Command::new("open")
        .arg(SCREEN_RECORDING_SETTINGS_URL)
        .status()
        .map_err(|error| format!("Unable to open capture settings: {error}"))?;
    Ok(())
}

#[tauri::command]
pub(crate) async fn request_microphone_access() -> Result<bool, String> {
    tauri::async_runtime::spawn_blocking(macos_microphone::request_access)
        .await
        .map_err(|error| format!("Unable to request microphone access: {error}"))?
}

#[tauri::command]
pub(crate) fn open_microphone_settings() -> Result<(), String> {
    Command::new("open")
        .arg(MICROPHONE_SETTINGS_URL)
        .status()
        .map_err(|error| format!("Unable to open microphone settings: {error}"))?;
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
pub(crate) fn open_isolated_desktop(browser_url: String) -> Result<(), String> {
    if !browser_url.starts_with("http://127.0.0.1:") {
        return Err("Only local isolated desktops can be opened.".to_string());
    }
    Command::new("open")
        .arg(browser_url)
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
