import { Volume2, VolumeX } from "lucide-react";

import { Button, Card } from "../../components/ui";
import { canToggleTargetAudioMute, targetAudioMuted } from "../../lib/job-state";
import type { JobResponse } from "../../lib/types";

export function LiveCaptureControls({
  job,
  mutePending = false,
  onSetMuted,
}: {
  job: JobResponse | null;
  mutePending?: boolean;
  onSetMuted: (jobId: string, muted: boolean) => void;
}) {
  if (!job || !canToggleTargetAudioMute(job)) {
    return null;
  }

  const muted = targetAudioMuted(job);
  const Icon = muted ? Volume2 : VolumeX;

  return (
    <Card className="live-controls-card">
      <div className="card-heading-row">
        <div>
          <p className="eyebrow">App audio</p>
          <h2>{muted ? "Muted for you" : "Playing for you"}</h2>
        </div>
        <Button disabled={mutePending} onClick={() => onSetMuted(job.id, !muted)} variant="secondary">
          <Icon aria-hidden="true" size={16} />
          {mutePending ? "Updating..." : muted ? "Unmute app" : "Mute app"}
        </Button>
      </div>
    </Card>
  );
}
