import type { HealthStatusResponse } from "../../lib/types";
import { Badge, Card } from "../../components/ui";

export function HealthPanel({ health }: { health: HealthStatusResponse | null }) {
  const entries = health
    ? [
        ["Desktop", health.desktop],
        ["Deepgram", health.deepgram],
        ["OpenClaw", health.openclaw],
      ]
    : [];
  return (
    <Card>
      <p className="eyebrow">Readiness</p>
      <h2>System checks</h2>
      <div className="health-grid">
        {entries.map(([label, result]) => (
          <div className="health-cell" key={label as string}>
            <span>{label as string}</span>
            <Badge tone={(result as HealthStatusResponse["desktop"]).ok ? "good" : "warn"}>{(result as HealthStatusResponse["desktop"]).status}</Badge>
          </div>
        ))}
      </div>
    </Card>
  );
}
