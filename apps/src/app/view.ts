export type View = "overview" | "capture" | "live" | "captures" | "voice-notes" | "settings";

const viewPaths: Record<View, string> = {
  overview: "/",
  capture: "/capture",
  live: "/live",
  captures: "/captures",
  "voice-notes": "/voice-notes",
  settings: "/settings",
};

const pathViews = new Map<string, View>(Object.entries(viewPaths).map(([view, path]) => [path, view as View]));
const legacyPaths = new Map<string, View>([
  ["/dashboard", "overview"],
  ["/jobs", "captures"],
]);

export function hashForView(view: View) {
  return `#${viewPaths[view]}`;
}

export function viewFromHash(hash: string): View {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  return pathViews.get(path) ?? legacyPaths.get(path) ?? "overview";
}
