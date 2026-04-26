import { Activity, Captions, ListChecks, MonitorUp, Settings } from "lucide-react";

import thirdeyeLogoUrl from "../../../../assets/logo.png";
import type { View } from "../../app/view";

export function Navigation({ view, setView, liveAvailable }: { view: View; setView: (view: View) => void; liveAvailable: boolean }) {
  const liveItems: Array<{ view: View; label: string; icon: typeof Activity }> = liveAvailable ? [{ view: "live" as const, label: "Live", icon: Captions }] : [];
  const items: Array<{ view: View; label: string; icon: typeof Activity }> = [
    { view: "dashboard", label: "Overview", icon: Activity },
    { view: "capture", label: "Capture", icon: MonitorUp },
    { view: "jobs", label: "Jobs", icon: ListChecks },
    ...liveItems,
    { view: "settings", label: "Settings", icon: Settings },
  ];

  return (
    <aside className="sidebar">
      <div className="brand">
        <img alt="thirdeye logo" className="brand-logo" src={thirdeyeLogoUrl} />
      </div>
      <nav className="nav-list" aria-label="Main views">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              aria-current={view === item.view ? "page" : undefined}
              className={view === item.view ? "nav-item nav-item-active" : "nav-item"}
              key={item.view}
              onClick={() => setView(item.view)}
              type="button"
            >
              <Icon aria-hidden="true" size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
