import { AudioLines, Mic, MicOff, Volume2, VolumeX } from "lucide-react";

import { Button, Card } from "../../components/ui";
import {
  canToggleEchoCancellation,
  canToggleMicrophoneRecording,
  canToggleTargetAudioMute,
  echoCancellationEnabled,
  recordMicrophoneEnabled,
  targetAudioMuted,
} from "../../lib/job-state";
import type { JobResponse } from "../../lib/types";

export function LiveCaptureControls({
  job,
  echoCancellationPending = false,
  microphonePending = false,
  mutePending = false,
  onSetEchoCancellation,
  onSetRecordMicrophone,
  onSetMuted,
}: {
  job: JobResponse | null;
  echoCancellationPending?: boolean;
  microphonePending?: boolean;
  mutePending?: boolean;
  onSetEchoCancellation: (jobId: string, enabled: boolean) => void;
  onSetRecordMicrophone: (jobId: string, enabled: boolean) => void;
  onSetMuted: (jobId: string, muted: boolean) => void;
}) {
  const canToggleAudioMute = Boolean(job && canToggleTargetAudioMute(job));
  const canToggleMicrophone = Boolean(job && canToggleMicrophoneRecording(job));
  const canToggleEcho = Boolean(job && canToggleEchoCancellation(job));
  if (!job || (!canToggleAudioMute && !canToggleMicrophone && !canToggleEcho)) {
    return null;
  }

  const muted = targetAudioMuted(job);
  const microphoneEnabled = recordMicrophoneEnabled(job);
  const echoEnabled = echoCancellationEnabled(job);
  const AudioIcon = muted ? Volume2 : VolumeX;
  const MicrophoneIcon = microphoneEnabled ? MicOff : Mic;

  return (
    <Card className="live-controls-card">
      {canToggleAudioMute ? (
        <div className="live-control-row">
          <div>
            <p className="eyebrow">App audio</p>
            <h2>{muted ? "Muted for you" : "Playing for you"}</h2>
            {microphoneEnabled ? <p className="helper-text">Stop microphone recording before muting this app.</p> : null}
          </div>
          <Button disabled={mutePending || microphoneEnabled} onClick={() => onSetMuted(job.id, !muted)} variant="secondary">
            <AudioIcon aria-hidden="true" size={16} />
            {mutePending ? "Updating..." : muted ? "Unmute app" : "Mute app"}
          </Button>
        </div>
      ) : null}
      {canToggleMicrophone ? (
        <div className="live-control-row">
          <div>
            <p className="eyebrow">Microphone</p>
            <h2>{microphoneEnabled ? "Recording microphone" : "Microphone off"}</h2>
            {muted ? <p className="helper-text">Unmute the app before recording microphone.</p> : null}
          </div>
          <Button disabled={microphonePending || muted} onClick={() => onSetRecordMicrophone(job.id, !microphoneEnabled)} variant="secondary">
            <MicrophoneIcon aria-hidden="true" size={16} />
            {microphonePending ? "Updating..." : microphoneEnabled ? "Stop microphone" : "Record microphone"}
          </Button>
        </div>
      ) : null}
      {canToggleEcho ? (
        <div className="live-control-row">
          <div>
            <p className="eyebrow">Speaker echo</p>
            <h2>{echoEnabled ? "Echo reduced" : "Echo reduction off"}</h2>
            <p className="helper-text">Keeps session audio playing while cleaning your microphone.</p>
          </div>
          <Button disabled={echoCancellationPending} onClick={() => onSetEchoCancellation(job.id, !echoEnabled)} variant="secondary">
            <AudioLines aria-hidden="true" size={16} />
            {echoCancellationPending ? "Updating..." : echoEnabled ? "Turn off" : "Reduce speaker echo"}
          </Button>
        </div>
      ) : null}
    </Card>
  );
}
