import { MonitorUp } from "lucide-react";

import { Badge, Button } from "../../components/ui";
import { openScreenRecordingSettings } from "../../lib/services";

export function ScreenRecordingPermissionNotice() {
  return (
    <div className="permission-notice" role="alert">
      <Badge tone="warn">Needs access</Badge>
      <div>
        <p className="permission-title">Capture access is blocked</p>
        <p className="permission-copy">Allow thirdeye in Screen & System Audio Recording, then return here and refresh targets.</p>
      </div>
      <Button onClick={() => void openScreenRecordingSettings()} type="button" variant="secondary">
        <MonitorUp aria-hidden="true" size={16} />
        Open capture settings
      </Button>
    </div>
  );
}
