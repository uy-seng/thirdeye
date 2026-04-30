use crate::runtime::application_support_root;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Clone, Debug, Deserialize, PartialEq)]
struct SilenceAlertPayload {
    title: String,
    body: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SilenceAppAlertPayload {
    job_id: String,
    title: String,
    body: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct SilenceNotificationMonitorPayload {
    job_id: String,
    title: String,
    timeout_ms: u64,
    elapsed_ms: Option<u64>,
    alert: Option<SilenceAlertPayload>,
    one_shot: Option<bool>,
}

#[derive(Clone, Default)]
pub(crate) struct SilenceNotificationMonitor {
    state: Arc<Mutex<SilenceNotificationMonitorState>>,
}

#[derive(Default)]
struct SilenceNotificationMonitorState {
    active: HashMap<String, SilenceNotificationJob>,
    generation: u64,
}

struct SilenceNotificationJob {
    title: String,
    timeout: Duration,
    last_activity: Instant,
    generation: u64,
    alert: Option<SilenceAlertPayload>,
    one_shot: bool,
}

#[derive(Debug, PartialEq)]
enum SilenceNotificationMonitorAction {
    Continue,
    Stop,
    Notify(SilenceAlertPayload),
}

struct SilenceNotificationMonitorProgress {
    elapsed: Duration,
    remaining: Duration,
    timeout: Duration,
}

impl SilenceNotificationMonitorState {
    fn start_job(
        &mut self,
        job_id: String,
        title: String,
        timeout: Duration,
        now: Instant,
        alert: Option<SilenceAlertPayload>,
        one_shot: bool,
    ) -> u64 {
        self.generation = self.generation.wrapping_add(1);
        self.active.insert(
            job_id,
            SilenceNotificationJob {
                title,
                timeout,
                last_activity: now,
                generation: self.generation,
                alert,
                one_shot,
            },
        );
        self.generation
    }

    fn record_activity(&mut self, job_id: &str, now: Instant) {
        if let Some(job) = self.active.get_mut(job_id) {
            job.last_activity = now;
        }
    }

    fn stop_job(&mut self, job_id: &str) {
        self.active.remove(job_id);
    }

    fn next_action(
        &mut self,
        job_id: &str,
        generation: u64,
        now: Instant,
    ) -> SilenceNotificationMonitorAction {
        let Some(job) = self.active.get_mut(job_id) else {
            return SilenceNotificationMonitorAction::Stop;
        };
        if job.generation != generation {
            return SilenceNotificationMonitorAction::Stop;
        }
        if now.saturating_duration_since(job.last_activity) < job.timeout {
            return SilenceNotificationMonitorAction::Continue;
        }

        let payload = job
            .alert
            .clone()
            .unwrap_or_else(|| silence_notification_payload(&job.title, job.timeout));
        let one_shot = job.one_shot;
        if one_shot {
            self.active.remove(job_id);
        } else {
            job.last_activity = now;
        }
        SilenceNotificationMonitorAction::Notify(payload)
    }

    fn progress(
        &self,
        job_id: &str,
        generation: u64,
        now: Instant,
    ) -> Option<SilenceNotificationMonitorProgress> {
        let job = self.active.get(job_id)?;
        if job.generation != generation {
            return None;
        }
        let elapsed = now.saturating_duration_since(job.last_activity);
        let remaining = if elapsed >= job.timeout {
            Duration::ZERO
        } else {
            job.timeout - elapsed
        };
        Some(SilenceNotificationMonitorProgress {
            elapsed,
            remaining,
            timeout: job.timeout,
        })
    }
}

#[tauri::command]
pub(crate) fn start_silence_notification_monitor(
    app: AppHandle,
    monitor: State<'_, SilenceNotificationMonitor>,
    payload: SilenceNotificationMonitorPayload,
) -> Result<(), String> {
    let SilenceNotificationMonitorPayload {
        job_id,
        title,
        timeout_ms,
        elapsed_ms,
        alert,
        one_shot,
    } = payload;
    let log_title = sanitize_log_value(&title);
    let elapsed_ms = elapsed_ms.unwrap_or(0);
    let alert_override = alert.is_some();
    let one_shot = one_shot.unwrap_or(false);
    let timeout = Duration::from_millis(timeout_ms.max(1_000));
    let worker_job_id = job_id.clone();
    let state = monitor.state.clone();
    let generation = {
        let mut guard = state
            .lock()
            .map_err(|_| "Unable to start silence alert monitor.".to_string())?;
        let now = Instant::now();
        let elapsed = Duration::from_millis(elapsed_ms);
        let last_activity = now.checked_sub(elapsed).unwrap_or(now);
        guard.start_job(job_id, title, timeout, last_activity, alert, one_shot)
    };
    log_silence_notification_event(&format!(
        "silence-monitor start job_id={} generation={} title=\"{}\" timeout_ms={} elapsed_ms={} one_shot={} alert_override={}",
        worker_job_id,
        generation,
        log_title,
        timeout.as_millis(),
        elapsed_ms,
        one_shot,
        alert_override
    ));
    std::thread::spawn(move || {
        run_silence_notification_monitor(app, state, worker_job_id, generation)
    });
    Ok(())
}

#[tauri::command]
pub(crate) fn record_silence_notification_activity(
    monitor: State<'_, SilenceNotificationMonitor>,
    job_id: String,
) -> Result<(), String> {
    let mut guard = monitor
        .state
        .lock()
        .map_err(|_| "Unable to update silence alert monitor.".to_string())?;
    guard.record_activity(&job_id, Instant::now());
    log_silence_notification_event(&format!("silence-monitor activity job_id={job_id}"));
    Ok(())
}

#[tauri::command]
pub(crate) fn stop_silence_notification_monitor(
    monitor: State<'_, SilenceNotificationMonitor>,
    job_id: String,
) -> Result<(), String> {
    let mut guard = monitor
        .state
        .lock()
        .map_err(|_| "Unable to stop silence alert monitor.".to_string())?;
    guard.stop_job(&job_id);
    log_silence_notification_event(&format!("silence-monitor stop job_id={job_id}"));
    Ok(())
}

fn run_silence_notification_monitor(
    app: AppHandle,
    state: Arc<Mutex<SilenceNotificationMonitorState>>,
    job_id: String,
    generation: u64,
) {
    log_silence_notification_event(&format!(
        "silence-monitor worker-start job_id={job_id} generation={generation}"
    ));
    let mut last_progress_log = Instant::now()
        .checked_sub(Duration::from_secs(15))
        .unwrap_or_else(Instant::now);
    loop {
        std::thread::sleep(Duration::from_secs(1));
        let now = Instant::now();
        let (action, progress) = match state.lock() {
            Ok(mut guard) => {
                let action = guard.next_action(&job_id, generation, now);
                let progress = if matches!(action, SilenceNotificationMonitorAction::Continue) {
                    guard.progress(&job_id, generation, now)
                } else {
                    None
                };
                (action, progress)
            }
            Err(_) => {
                log_silence_notification_event(&format!(
                    "silence-monitor worker-stop job_id={job_id} generation={generation} reason=state-lock-failed"
                ));
                return;
            }
        };
        match action {
            SilenceNotificationMonitorAction::Continue => {
                if last_progress_log.elapsed() >= Duration::from_secs(15) {
                    if let Some(progress) = progress {
                        log_silence_notification_event(&format!(
                            "silence-monitor waiting job_id={} generation={} elapsed_ms={} remaining_ms={} timeout_ms={}",
                            job_id,
                            generation,
                            progress.elapsed.as_millis(),
                            progress.remaining.as_millis(),
                            progress.timeout.as_millis()
                        ));
                    }
                    last_progress_log = Instant::now();
                }
            }
            SilenceNotificationMonitorAction::Stop => {
                log_silence_notification_event(&format!(
                    "silence-monitor worker-stop job_id={job_id} generation={generation} reason=stopped-or-stale"
                ));
                return;
            }
            SilenceNotificationMonitorAction::Notify(payload) => {
                log_silence_notification_event(&format!(
                    "silence-monitor notify job_id={} generation={} title=\"{}\"",
                    job_id,
                    generation,
                    sanitize_log_value(&payload.title)
                ));
                emit_silence_app_alert(&app, &job_id, generation, &payload);
            }
        }
    }
}

fn emit_silence_app_alert(
    app: &AppHandle,
    job_id: &str,
    generation: u64,
    payload: &SilenceAlertPayload,
) {
    let event_payload = SilenceAppAlertPayload {
        job_id: job_id.to_string(),
        title: payload.title.clone(),
        body: payload.body.clone(),
    };
    match app.emit("silence-alert", event_payload) {
        Ok(()) => log_silence_notification_event(&format!(
            "silence-monitor app-alert emitted job_id={job_id} generation={generation}"
        )),
        Err(error) => log_silence_notification_event(&format!(
            "silence-monitor app-alert failed job_id={} generation={} error=\"{}\"",
            job_id,
            generation,
            sanitize_log_value(&error.to_string())
        )),
    }

    match app.get_webview_window("main") {
        Some(window) => {
            log_window_attention_result("show", job_id, generation, window.show());
            log_window_attention_result("unminimize", job_id, generation, window.unminimize());
            log_window_attention_result("maximize", job_id, generation, window.maximize());
            log_window_attention_result("focus", job_id, generation, window.set_focus());
        }
        None => log_silence_notification_event(&format!(
            "silence-monitor window attention failed job_id={job_id} generation={generation} error=\"main window not found\""
        )),
    }
}

fn log_window_attention_result(
    action: &str,
    job_id: &str,
    generation: u64,
    result: tauri::Result<()>,
) {
    match result {
        Ok(()) => log_silence_notification_event(&format!(
            "silence-monitor window {action} requested job_id={job_id} generation={generation}"
        )),
        Err(error) => log_silence_notification_event(&format!(
            "silence-monitor window {} failed job_id={} generation={} error=\"{}\"",
            action,
            job_id,
            generation,
            sanitize_log_value(&error.to_string())
        )),
    }
}

fn log_silence_notification_event(event: &str) {
    let line = format!("{} {}\n", unix_timestamp_millis(), event);
    if let Ok(runtime_root) = application_support_root() {
        let log_dir = runtime_root.join("logs");
        if fs::create_dir_all(&log_dir).is_ok() {
            if let Ok(mut file) = OpenOptions::new()
                .create(true)
                .append(true)
                .open(log_dir.join("silence-notifications.log"))
            {
                let _ = file.write_all(line.as_bytes());
                return;
            }
        }
    }
    eprint!("[silence-notifications] {line}");
}

fn unix_timestamp_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0)
}

fn sanitize_log_value(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character == '\n' || character == '\r' {
                ' '
            } else {
                character
            }
        })
        .collect()
}

fn silence_notification_payload(job_title: &str, timeout: Duration) -> SilenceAlertPayload {
    SilenceAlertPayload {
        title: "No speech detected".to_string(),
        body: format!(
            "No new transcript has appeared for {} in {job_title}.",
            format_silence_duration(timeout)
        ),
    }
}

fn format_silence_duration(timeout: Duration) -> String {
    let minutes = ((timeout.as_secs() + 30) / 60).max(1);
    format!(
        "{minutes} {}",
        if minutes == 1 { "minute" } else { "minutes" }
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn silence_monitor_triggers_without_webview_ticks() {
        let started_at = Instant::now();
        let mut state = SilenceNotificationMonitorState::default();
        let generation = state.start_job(
            "job-1".to_string(),
            "Authorized session".to_string(),
            Duration::from_secs(120),
            started_at,
            None,
            false,
        );

        assert!(matches!(
            state.next_action("job-1", generation, started_at + Duration::from_secs(119)),
            SilenceNotificationMonitorAction::Continue
        ));

        match state.next_action("job-1", generation, started_at + Duration::from_secs(120)) {
            SilenceNotificationMonitorAction::Notify(payload) => {
                assert_eq!(payload.title, "No speech detected");
                assert_eq!(
                    payload.body,
                    "No new transcript has appeared for 2 minutes in Authorized session."
                );
            }
            action => panic!("expected notification action, got {action:?}"),
        }
    }

    #[test]
    fn silence_monitor_activity_resets_due_time() {
        let started_at = Instant::now();
        let mut state = SilenceNotificationMonitorState::default();
        let generation = state.start_job(
            "job-1".to_string(),
            "Authorized session".to_string(),
            Duration::from_secs(120),
            started_at,
            None,
            false,
        );

        state.record_activity("job-1", started_at + Duration::from_secs(90));

        assert!(matches!(
            state.next_action("job-1", generation, started_at + Duration::from_secs(120)),
            SilenceNotificationMonitorAction::Continue
        ));
        assert!(matches!(
            state.next_action("job-1", generation, started_at + Duration::from_secs(210)),
            SilenceNotificationMonitorAction::Notify(_)
        ));
    }

    #[test]
    fn silence_monitor_can_start_after_elapsed_inactivity() {
        let now = Instant::now();
        let mut state = SilenceNotificationMonitorState::default();
        let generation = state.start_job(
            "job-1".to_string(),
            "Authorized session".to_string(),
            Duration::from_secs(120),
            now - Duration::from_secs(121),
            None,
            false,
        );

        assert!(matches!(
            state.next_action("job-1", generation, now),
            SilenceNotificationMonitorAction::Notify(_)
        ));
    }

    #[test]
    fn silence_monitor_keeps_independent_jobs_active() {
        let started_at = Instant::now();
        let mut state = SilenceNotificationMonitorState::default();
        let capture_generation = state.start_job(
            "job-1".to_string(),
            "Authorized session".to_string(),
            Duration::from_secs(120),
            started_at,
            None,
            false,
        );
        let test_generation = state.start_job(
            "test-alert".to_string(),
            "Test alert".to_string(),
            Duration::from_secs(15),
            started_at,
            Some(SilenceAlertPayload {
                title: "Test silence alert".to_string(),
                body: "This is a 15-second test using the same silence alert timer.".to_string(),
            }),
            true,
        );

        assert!(matches!(
            state.next_action(
                "job-1",
                capture_generation,
                started_at + Duration::from_secs(15)
            ),
            SilenceNotificationMonitorAction::Continue
        ));
        match state.next_action(
            "test-alert",
            test_generation,
            started_at + Duration::from_secs(15),
        ) {
            SilenceNotificationMonitorAction::Notify(payload) => {
                assert_eq!(payload.title, "Test silence alert");
                assert_eq!(
                    payload.body,
                    "This is a 15-second test using the same silence alert timer."
                );
            }
            action => panic!("expected notification action, got {action:?}"),
        }
        assert!(matches!(
            state.next_action(
                "test-alert",
                test_generation,
                started_at + Duration::from_secs(16)
            ),
            SilenceNotificationMonitorAction::Stop
        ));
        assert!(matches!(
            state.next_action(
                "job-1",
                capture_generation,
                started_at + Duration::from_secs(120)
            ),
            SilenceNotificationMonitorAction::Notify(_)
        ));
    }

    #[test]
    fn silence_monitor_stops_stale_workers_for_restarted_job() {
        let started_at = Instant::now();
        let mut state = SilenceNotificationMonitorState::default();
        let old_generation = state.start_job(
            "job-1".to_string(),
            "Authorized session".to_string(),
            Duration::from_secs(120),
            started_at,
            None,
            false,
        );
        let _new_generation = state.start_job(
            "job-1".to_string(),
            "Authorized session".to_string(),
            Duration::from_secs(120),
            started_at,
            None,
            false,
        );

        assert!(matches!(
            state.next_action(
                "job-1",
                old_generation,
                started_at + Duration::from_secs(120)
            ),
            SilenceNotificationMonitorAction::Stop
        ));
    }
}
