import { MonitorUp, Terminal } from "lucide-react";

import { ServiceStrip } from "../../components/services/ServiceStrip";
import { Button, Card } from "../../components/ui";
import { openLogsFolder, openScreenRecordingSettings } from "../../lib/services";
import type { DesktopSession, ServiceStatus } from "../../lib/types";
import { DesktopSessionsPanel } from "../capture/DesktopSessionsPanel";

export function SettingsPanel({
  desktops,
  serviceStatus,
  onCreateDesktop,
  onDesktopDestroyed,
  onDesktopsRefresh,
  onRefresh,
  onStart,
  onStop,
}: {
  desktops: DesktopSession[];
  serviceStatus: ServiceStatus | null;
  onCreateDesktop: (label: string) => Promise<void>;
  onDesktopDestroyed: () => Promise<void>;
  onDesktopsRefresh: () => Promise<void>;
  onRefresh: () => void;
  onStart: () => void;
  onStop: () => void;
}) {
  return (
    <div className="grid-two">
      <ServiceStrip onRefresh={onRefresh} onStart={onStart} onStop={onStop} status={serviceStatus} />
      <DesktopSessionsPanel desktops={desktops} onCreate={onCreateDesktop} onDestroyed={onDesktopDestroyed} onRefresh={onDesktopsRefresh} />
      <Card>
        <p className="eyebrow">macOS access</p>
        <h2>Local tools</h2>
        <p className="muted">Use these when capture access is blocked or you need to inspect service logs.</p>
        <div className="toolbar vertical">
          <Button onClick={() => void openScreenRecordingSettings()} variant="secondary">
            <MonitorUp aria-hidden="true" size={16} />
            Capture permissions
          </Button>
          <Button onClick={() => void openLogsFolder()} variant="secondary">
            <Terminal aria-hidden="true" size={16} />
            Open logs
          </Button>
        </div>
        <p className="mono-line">{serviceStatus?.runtime_root}</p>
      </Card>
    </div>
  );
}
