import { ExternalLink, Plus, RefreshCw, Trash2 } from "lucide-react";
import { FormEvent, useState } from "react";

import { Badge, Button, Card, TextInput } from "../../components/ui";
import { destroyDesktop } from "../../lib/api";
import { desktopSessionActivityLabel } from "../../lib/job-state";
import { openIsolatedDesktop } from "../../lib/services";
import type { DesktopSession } from "../../lib/types";

type DesktopSessionsPanelProps = {
  desktops: DesktopSession[];
  onCreate: (label: string) => Promise<void>;
  onDestroyed: () => Promise<void>;
  onRefresh: () => Promise<void>;
};

function desktopTone(status: DesktopSession["status"]): "neutral" | "good" | "warn" | "bad" | "info" {
  if (status === "ready") {
    return "good";
  }
  if (status === "starting") {
    return "info";
  }
  if (status === "error") {
    return "bad";
  }
  return "warn";
}

export function DesktopSessionsPanel({ desktops, onCreate, onDestroyed, onRefresh }: DesktopSessionsPanelProps) {
  const [label, setLabel] = useState("Meeting desktop");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [destroyingId, setDestroyingId] = useState<string | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await onCreate(label.trim() || "Meeting desktop");
      setLabel("Meeting desktop");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create isolated desktop.");
    } finally {
      setBusy(false);
    }
  }

  async function destroy(desktop: DesktopSession) {
    setDestroyingId(desktop.id);
    setMessage("");
    try {
      await destroyDesktop(desktop.id);
      await onDestroyed();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to destroy isolated desktop.");
    } finally {
      setDestroyingId(null);
    }
  }

  return (
    <Card>
      <div className="card-heading-row">
        <div>
          <p className="eyebrow">Isolated desktops</p>
          <h2>Desktop workspaces</h2>
        </div>
        <Badge tone={desktops.length > 0 ? "info" : "neutral"}>{desktops.length} ready</Badge>
      </div>
      <form className="desktop-create-row" onSubmit={create}>
        <label>
          Desktop name
          <TextInput onChange={(event) => setLabel(event.target.value)} value={label} />
        </label>
        <Button disabled={busy} type="submit">
          <Plus aria-hidden="true" size={16} />
          {busy ? "Creating..." : "Create isolated desktop"}
        </Button>
        <Button onClick={() => void onRefresh()} type="button" variant="secondary">
          <RefreshCw aria-hidden="true" size={16} />
          Refresh
        </Button>
      </form>
      <div className="desktop-session-list">
        {desktops.length === 0 ? <p className="muted">Create a desktop before starting an isolated capture.</p> : null}
        {desktops.map((desktop) => (
          <div className="desktop-session-row" key={desktop.id}>
            <span>
              <strong>{desktop.label}</strong>
              <small>{desktopSessionActivityLabel(desktop)}</small>
            </span>
            <Badge tone={desktopTone(desktop.status)}>{desktop.status === "ready" ? "Ready" : desktop.status}</Badge>
            <Button disabled={desktop.status !== "ready"} onClick={() => void openIsolatedDesktop(desktop.browser_url)} type="button" variant="secondary">
              <ExternalLink aria-hidden="true" size={16} />
              Open
            </Button>
            <Button disabled={Boolean(desktop.active_job_id) || destroyingId === desktop.id} onClick={() => void destroy(desktop)} type="button" variant="danger">
              <Trash2 aria-hidden="true" size={16} />
              {destroyingId === desktop.id ? "Destroying..." : "Destroy"}
            </Button>
          </div>
        ))}
      </div>
      {message ? (
        <p aria-live="polite" className="status-message" role="status">
          {message}
        </p>
      ) : null}
    </Card>
  );
}
