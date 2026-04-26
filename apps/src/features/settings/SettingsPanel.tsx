import { MonitorUp, Terminal } from "lucide-react";

import { ServiceStrip } from "../../components/services/ServiceStrip";
import { Button, Card } from "../../components/ui";
import { openLogsFolder, openScreenRecordingSettings } from "../../lib/services";
import type { ServiceStatus } from "../../lib/types";

export function SettingsPanel({
  serviceStatus,
  onRefresh,
  onStart,
  onStop,
}: {
  serviceStatus: ServiceStatus | null;
  onRefresh: () => void;
  onStart: () => void;
  onStop: () => void;
}) {
  return (
    <div className="grid-two">
      <ServiceStrip onRefresh={onRefresh} onStart={onStart} onStop={onStop} status={serviceStatus} />
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
