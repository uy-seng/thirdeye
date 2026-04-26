import { FormEvent, useEffect, useState } from "react";

import { Button, Card, Select, TextInput } from "../../components/ui";
import { getCaptureTargets, startCapture } from "../../lib/api";
import type { CaptureBackend, CaptureTarget, JobResponse } from "../../lib/types";
import { ScreenRecordingPermissionNotice } from "./ScreenRecordingPermissionNotice";
import { isScreenRecordingPermissionError, targetGroups, targetLabel } from "./captureTargets";

export function StartCapturePanel({ onCreated }: { onCreated: (job: JobResponse) => void }) {
  const [title, setTitle] = useState("Authorized session");
  const [backend, setBackend] = useState<CaptureBackend>("macos_local");
  const [targets, setTargets] = useState<CaptureTarget[]>([]);
  const [targetId, setTargetId] = useState("");
  const [screenRecord, setScreenRecord] = useState(true);
  const [muteTargetAudio, setMuteTargetAudio] = useState(false);
  const [generateSummary, setGenerateSummary] = useState(true);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const selectedTarget = targets.find((target) => target.id === targetId);
  const permissionBlocked = backend === "macos_local" && isScreenRecordingPermissionError(message);
  const canMuteTargetAudio = backend === "macos_local" && Boolean(selectedTarget && ["application", "window"].includes(selectedTarget.kind));
  const muteTargetHelp = "This mutes the selected app while capture runs. The transcript and recording still receive audio.";

  async function loadTargets(nextBackend = backend) {
    setMessage("");
    if (nextBackend === "docker_desktop") {
      setTargets([]);
      setTargetId("");
      return;
    }
    try {
      const payload = await getCaptureTargets(nextBackend);
      setTargets(payload.targets);
      setTargetId((current) => (payload.targets.some((target) => target.id === current) ? current : payload.targets[0]?.id ?? ""));
      if (payload.targets.length === 0) {
        setMessage("No local displays or windows are available yet.");
      }
    } catch (error) {
      setTargets([]);
      setTargetId("");
      setMessage(error instanceof Error ? error.message : "Unable to load capture targets.");
    }
  }

  useEffect(() => {
    void loadTargets(backend);
  }, [backend]);

  useEffect(() => {
    if (!canMuteTargetAudio) {
      setMuteTargetAudio(false);
    }
  }, [canMuteTargetAudio]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (backend === "macos_local" && !selectedTarget) {
      setMessage("Choose what to capture before starting.");
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
          generate_summary: generateSummary,
          mute_target_audio: canMuteTargetAudio ? muteTargetAudio : false,
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
        <div className="capture-options" aria-label="Session options">
          <label className="option-row">
            <input checked={screenRecord} onChange={(event) => setScreenRecord(event.target.checked)} type="checkbox" />
            <span>
              <strong>Screen record</strong>
              <small>Save a video file with the transcript.</small>
            </span>
          </label>
          <label className="option-row">
            <input
              checked={muteTargetAudio}
              disabled={!canMuteTargetAudio}
              onChange={(event) => setMuteTargetAudio(event.target.checked)}
              type="checkbox"
            />
            <span>
              <strong>Mute this app for me</strong>
              <small>{canMuteTargetAudio ? muteTargetHelp : "Choose an app or window to use silent capture."}</small>
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
          <Button disabled={busy || (backend === "macos_local" && !selectedTarget)} type="submit">
            {busy ? "Starting..." : "Start capture"}
          </Button>
          <Button onClick={() => void loadTargets()} type="button" variant="secondary">
            Refresh targets
          </Button>
        </div>
        {permissionBlocked ? <ScreenRecordingPermissionNotice /> : message ? <p className="form-message">{message}</p> : null}
      </form>
    </Card>
  );
}
