mod app_commands;
mod local_services;
mod runtime;
mod silence_notifications;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(local_services::AppServiceManager::default())
        .manage(silence_notifications::SilenceNotificationMonitor::default())
        .invoke_handler(tauri::generate_handler![
            local_services::start_services,
            local_services::stop_services,
            local_services::service_status,
            app_commands::open_screen_recording_settings,
            silence_notifications::start_silence_notification_monitor,
            silence_notifications::record_silence_notification_activity,
            silence_notifications::stop_silence_notification_monitor,
            app_commands::open_logs_folder,
            app_commands::open_isolated_desktop,
            app_commands::open_artifact_in_finder
        ])
        .run(tauri::generate_context!())
        .expect("error while running thirdeye");
}
