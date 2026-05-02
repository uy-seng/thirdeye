import { Mic, MicOff, Volume2, VolumeX } from "lucide-react";

import { Button, Card } from "../../components/ui";
import {
  canToggleMicrophoneRecording,
  canToggleTargetAudioMute,
  recordMicrophoneEnabled,
  targetAudioMuted,
} from "../../lib/job-state";
import type { JobResponse } from "../../lib/types";

export function LiveCaptureControls({
  job,
  microphonePending = false,
  mutePending = false,
  onSetRecordMicrophone,
  onSetMuted,
}: {
  job: JobResponse | null;
  microphonePending?: boolean;
  mutePending?: boolean;
  onSetRecordMicrophone: (jobId: string, enabled: boolean) => void;
  onSetMuted: (jobId: string, muted: boolean) => void;
}) {
  const canToggleAudioMute = Boolean(job && canToggleTargetAudioMute(job));
  const canToggleMicrophone = Boolean(job && canToggleMicrophoneRecording(job));
  if (!job || (!canToggleAudioMute && !canToggleMicrophone)) {
    return null;
  }

  const muted = targetAudioMuted(job);
  const microphoneEnabled = recordMicrophoneEnabled(job);
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
    </Card>
  );
}
