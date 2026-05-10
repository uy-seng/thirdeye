export type View = "capture" | "live" | "voice-notes" | "settings";

const viewPaths: Record<View, string> = {
  capture: "/capture",
  live: "/live",
  "voice-notes": "/voice-notes",
  settings: "/settings",
};

const pathViews = new Map<string, View>(Object.entries(viewPaths).map(([view, path]) => [path, view as View]));
const legacyPaths = new Map<string, View>([
  ["/", "capture"],
  ["/dashboard", "capture"],
  ["/captures", "capture"],
  ["/jobs", "capture"],
]);

export function hashForView(view: View) {
  return `#${viewPaths[view]}`;
}

export function viewFromHash(hash: string): View {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  return pathViews.get(path) ?? legacyPaths.get(path) ?? "capture";
}
