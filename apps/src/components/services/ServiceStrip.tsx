import { ExternalLink, Play, RefreshCw, Square } from "lucide-react";

import { openIsolatedDesktop } from "../../lib/services";
import type { ServiceStatus } from "../../lib/types";
import { Badge, Button, Card } from "../ui";

function serviceTone(running: boolean): "good" | "warn" {
  return running ? "good" : "warn";
}

export function ServiceStrip({ status, onRefresh, onStart, onStop }: { status: ServiceStatus | null; onRefresh: () => void; onStart: () => void; onStop: () => void }) {
  return (
    <Card className="service-strip">
      <div className="card-heading-row">
        <div>
          <p className="eyebrow">Local services</p>
          <h2>App runtime</h2>
        </div>
        <div className="toolbar">
          <Button onClick={onStart} variant="secondary">
            <Play aria-hidden="true" size={16} />
            Start
          </Button>
          <Button onClick={onStop} variant="secondary">
            <Square aria-hidden="true" size={16} />
            Stop
          </Button>
          <Button onClick={onRefresh} variant="quiet">
            <RefreshCw aria-hidden="true" size={16} />
            Refresh
          </Button>
        </div>
      </div>
      <div className="service-grid">
        {(status?.reports ?? []).map((report) => {
          const isIsolatedDesktop = report.name === "Isolated desktop";
          return (
            <div className="service-row" key={report.name}>
              <span>{report.name}</span>
              <Badge tone={serviceTone(report.running)}>{report.running ? "Running" : "Stopped"}</Badge>
              <small>{report.detail}</small>
              {isIsolatedDesktop ? (
                <Button className="service-row-action" onClick={() => void openIsolatedDesktop()} type="button" variant="secondary">
                  <ExternalLink aria-hidden="true" size={15} />
                  Open
                </Button>
              ) : null}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
