import { FolderOpen, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Card } from "../../components/ui";
import {
  canDeleteJob,
  canStopCapture,
  formatStateLabel,
  stateTone,
  stopCaptureButtonLabel,
  stopCaptureStatusMessage,
} from "../../lib/job-state";
import { openArtifactInFinder } from "../../lib/services";
import type { ArtifactFile, JobDetailResponse } from "../../lib/types";
import { targetLabel } from "../capture/captureTargets";

export type JobDetailProps = {
  job: JobDetailResponse | null;
  artifacts: ArtifactFile[];
  deleteConfirming?: boolean;
  deletePending?: boolean;
  onCancelDelete: () => void;
  onConfirmDelete: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  onStop: (jobId: string) => void;
  stopPending?: boolean;
};

export function JobDetail({
  job,
  artifacts,
  deleteConfirming = false,
  deletePending = false,
  onCancelDelete,
  onConfirmDelete,
  onDelete,
  onStop,
  stopPending = false,
}: JobDetailProps) {
  const [artifactMessage, setArtifactMessage] = useState("");

  if (!job) {
    return (
      <Card>
        <p className="eyebrow">Job workspace</p>
        <h2>Select a job</h2>
        <p className="muted">Choose a capture from the list to view details.</p>
      </Card>
    );
  }

  const stopStatus = stopCaptureStatusMessage(job.state, stopPending);
  const deleteStatus = deletePending
    ? "Deleting job..."
    : deleteConfirming
      ? "Delete this job and its files? This cannot be undone."
      : canDeleteJob(job.state)
        ? ""
        : "Stop the capture before deleting this job.";

  async function handleOpenArtifact(artifact: ArtifactFile) {
    setArtifactMessage(`Opening ${artifact.name} in Finder...`);
    try {
      await openArtifactInFinder(artifact.path);
      setArtifactMessage(`Opened ${artifact.name} in Finder.`);
    } catch (error) {
      setArtifactMessage(error instanceof Error ? error.message : typeof error === "string" ? error : "Finder could not open this file.");
    }
  }

  return (
    <Card>
      <div className="card-heading-row">
        <div>
          <p className="eyebrow">Job workspace</p>
          <h2>{job.title}</h2>
        </div>
        <Badge tone={stateTone(job.state, job.metadata_json)}>{formatStateLabel(job.state, job.metadata_json)}</Badge>
      </div>
      <div className="detail-grid">
        <div>
          <span className="detail-label">Capture source</span>
          <strong>{job.capture_backend === "macos_local" ? "This Mac" : "Isolated desktop"}</strong>
        </div>
        <div>
          <span className="detail-label">Target</span>
          <strong>{targetLabel(job.capture_target)}</strong>
        </div>
        <div>
          <span className="detail-label">Started</span>
          <strong>{job.started_at ? new Date(job.started_at).toLocaleString() : "Not started"}</strong>
        </div>
      </div>
      <div className="toolbar">
        <Button disabled={!canStopCapture(job.state, stopPending)} onClick={() => onStop(job.id)} variant="danger">
          {stopCaptureButtonLabel(job.state, stopPending)}
        </Button>
        <Button disabled={!canDeleteJob(job.state, deletePending || deleteConfirming)} onClick={() => onDelete(job.id)} variant="danger">
          <Trash2 aria-hidden="true" size={16} />
          {deletePending ? "Deleting..." : deleteConfirming ? "Confirm below" : "Delete job"}
        </Button>
      </div>
      {stopStatus ? (
        <p aria-live="polite" className="status-message" role="status">
          {stopStatus}
        </p>
      ) : null}
      {deleteStatus ? (
        <p aria-live="polite" className="status-message" role="status">
          <span>{deleteStatus}</span>
          {deleteConfirming && !deletePending ? (
            <span className="status-message-actions">
              <Button onClick={() => onConfirmDelete(job.id)} variant="danger">
                Delete now
              </Button>
              <Button onClick={onCancelDelete} variant="secondary">
                Cancel
              </Button>
            </span>
          ) : null}
        </p>
      ) : null}
      <h3>Files</h3>
      <div className="artifact-list">
        {artifacts.length === 0 ? <p className="muted">No files yet.</p> : null}
        {artifacts.map((artifact) => (
          <button className="artifact-row" key={artifact.name} onClick={() => void handleOpenArtifact(artifact)} type="button">
            <span>
              <FolderOpen aria-hidden="true" size={16} />
              <strong>{artifact.name}</strong>
            </span>
            <small>{Math.ceil(artifact.size_bytes / 1024)} KB</small>
          </button>
        ))}
      </div>
      {artifactMessage ? (
        <p aria-live="polite" className="status-message" role="status">
          {artifactMessage}
        </p>
      ) : null}
    </Card>
  );
}
