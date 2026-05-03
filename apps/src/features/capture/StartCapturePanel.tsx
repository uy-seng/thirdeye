import { FormEvent, useEffect, useState } from "react";

import { Button, Card, Select, TextInput } from "../../components/ui";
import { getCaptureTargets, startCapture } from "../../lib/api";
import { desktopCaptureBusyLabel } from "../../lib/job-state";
import { SILENCE_NOTIFICATION_TIMEOUT_MINUTES } from "../../lib/silence-notifications";
import type { CaptureBackend, CaptureTarget, JobResponse } from "../../lib/types";
import { ScreenRecordingPermissionNotice } from "./ScreenRecordingPermissionNotice";
import { isScreenRecordingPermissionError, targetGroups, targetLabel } from "./captureTargets";

type StartCapturePanelProps = {
  activeCaptures?: JobResponse[];
  onCreated: (job: JobResponse) => void;
  targetRefreshSignal?: unknown;
};

export function StartCapturePanel({ activeCaptures = [], onCreated, targetRefreshSignal = null }: StartCapturePanelProps) {
  const [title, setTitle] = useState("Authorized session");
  const [backend, setBackend] = useState<CaptureBackend>("macos_local");
  const [targets, setTargets] = useState<CaptureTarget[]>([]);
  const [targetId, setTargetId] = useState("");
  const [screenRecord, setScreenRecord] = useState(true);
  const [recordMicrophone, setRecordMicrophone] = useState(false);
  const [muteTargetAudio, setMuteTargetAudio] = useState(false);
  const [generateSummary, setGenerateSummary] = useState(true);
  const [notifyOnInactivity, setNotifyOnInactivity] = useState(true);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const selectedTarget = targets.find((target) => target.id === targetId);
  const permissionBlocked = backend === "macos_local" && isScreenRecordingPermissionError(message);
  const canRecordMicrophone = backend === "macos_local";
  const canMuteTargetAudio =
    backend === "macos_local" && !recordMicrophone && Boolean(selectedTarget && ["application", "window"].includes(selectedTarget.kind));
  const selectedTargetUnavailable = selectedTarget?.available === false;
  const macCaptureBlocked = backend === "macos_local" && activeCaptures.some((job) => job.capture_backend === "macos_local");
  const muteTargetHelp = "This mutes the selected app while capture runs. The transcript and recording still receive audio.";

  async function loadTargets(nextBackend = backend) {
    setMessage("");
    try {
      const payload = await getCaptureTargets(nextBackend);
      setTargets(payload.targets);
      setTargetId((current) => (payload.targets.some((target) => target.id === current) ? current : payload.targets[0]?.id ?? ""));
      if (payload.targets.length === 0) {
        setMessage(nextBackend === "docker_desktop" ? "Create an isolated desktop before starting." : "No local displays or windows are available yet.");
      }
    } catch (error) {
      setTargets([]);
      setTargetId("");
      setMessage(error instanceof Error ? error.message : "Unable to load capture options.");
    }
  }

  useEffect(() => {
    void loadTargets(backend);
  }, [backend, targetRefreshSignal]);

  useEffect(() => {
    if (!canMuteTargetAudio) {
      setMuteTargetAudio(false);
    }
  }, [canMuteTargetAudio]);

  useEffect(() => {
    if (!canRecordMicrophone) {
      setRecordMicrophone(false);
    }
  }, [canRecordMicrophone]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (selectedTargetUnavailable) {
      setMessage("Choose an available isolated desktop.");
      return;
    }
    if (macCaptureBlocked) {
      setMessage("Stop the active This Mac capture before starting another.");
      return;
    }
    if (backend === "macos_local" && !selectedTarget) {
      setMessage("Choose what to capture before starting.");
      return;
    }
    if (backend === "docker_desktop" && !selectedTarget) {
      setMessage("Create an isolated desktop before starting.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      onCreated(
        await startCapture({
          title,
          capture_backend: backend,
          capture_target: selectedTarget,
          record_screen: screenRecord,
          record_microphone: canRecordMicrophone ? recordMicrophone : false,
          generate_summary: generateSummary,
          mute_target_audio: canMuteTargetAudio && !recordMicrophone ? muteTargetAudio : false,
          notify_on_inactivity: notifyOnInactivity,
          silence_timeout_minutes: SILENCE_NOTIFICATION_TIMEOUT_MINUTES,
        }),
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to start capture.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <p className="eyebrow">New capture</p>
      <h2>Start a session</h2>
      <form className="stack" onSubmit={submit}>
        <label>
          Session name
          <TextInput onChange={(event) => setTitle(event.target.value)} required value={title} />
        </label>
        <label>
          Capture source
          <Select onChange={(event) => setBackend(event.target.value as CaptureBackend)} value={backend}>
            <option value="macos_local">This Mac</option>
            <option value="docker_desktop">Isolated desktop</option>
          </Select>
        </label>
        {backend === "macos_local" ? (
          <label>
            What to capture
            <Select disabled={targets.length === 0} onChange={(event) => setTargetId(event.target.value)} value={targetId}>
              {targetGroups(targets).map((group) => (
                <optgroup key={group.key} label={group.label}>
                  {group.targets.map((target) => (
                    <option key={target.id} value={target.id}>
                      {targetLabel(target)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </label>
        ) : null}
        {backend === "docker_desktop" ? (
          <label>
            Isolated desktop
            <Select disabled={targets.length === 0} onChange={(event) => setTargetId(event.target.value)} value={targetId}>
              {targets.map((target) => (
                <option disabled={target.available === false} key={target.id} value={target.id}>
                  {target.available === false ? `${targetLabel(target)} (${desktopCaptureBusyLabel(target.active_job_state)})` : targetLabel(target)}
                </option>
              ))}
            </Select>
          </label>
        ) : null}
        <div className="capture-options" aria-label="Session options">
          <label className="option-row">
            <input checked={screenRecord} onChange={(event) => setScreenRecord(event.target.checked)} type="checkbox" />
            <span>
              <strong>Screen record</strong>
              <small>Save a video file with the transcript.</small>
            </span>
          </label>
          {canRecordMicrophone ? (
            <label className="option-row">
              <input checked={recordMicrophone} onChange={(event) => setRecordMicrophone(event.target.checked)} type="checkbox" />
              <span>
                <strong>Record microphone</strong>
                <small>Use your microphone without changing other apps.</small>
              </span>
            </label>
          ) : null}
          {canMuteTargetAudio ? (
            <label className="option-row">
              <input checked={muteTargetAudio} onChange={(event) => setMuteTargetAudio(event.target.checked)} type="checkbox" />
              <span>
                <strong>Mute this app for me</strong>
                <small>{muteTargetHelp}</small>
              </span>
            </label>
          ) : null}
          <label className="option-row">
            <input checked={notifyOnInactivity} onChange={(event) => setNotifyOnInactivity(event.target.checked)} type="checkbox" />
            <span>
              <strong>Notify me about silence</strong>
              <small>Get an alert if no words appear for 2 minutes.</small>
            </span>
          </label>
          <label className="option-row">
            <input checked={generateSummary} onChange={(event) => setGenerateSummary(event.target.checked)} type="checkbox" />
            <span>
              <strong>Generate summary</strong>
              <small>Create the final summary when capture stops.</small>
            </span>
          </label>
        </div>
        <div className="toolbar">
          <Button
            disabled={busy || selectedTargetUnavailable || macCaptureBlocked || (backend === "macos_local" && !selectedTarget) || (backend === "docker_desktop" && !selectedTarget)}
            type="submit"
          >
            {busy ? "Starting..." : "Start capture"}
          </Button>
          <Button onClick={() => void loadTargets()} type="button" variant="secondary">
            Refresh targets
          </Button>
        </div>
        {permissionBlocked ? (
          <ScreenRecordingPermissionNotice />
        ) : message ? (
          <p className="form-message">{message}</p>
        ) : null}
      </form>
    </Card>
  );
}
