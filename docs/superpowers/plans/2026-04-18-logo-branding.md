# Logo Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text-first branding in the controller web app and README with the standalone logo asset the user added under `assets/`.

**Architecture:** Keep the root `assets/` files as the source branding inputs, copy the web-served files into `controller/web/public/branding/`, and route all UI branding through a shared logo component backed by `controller/web/lib/brand.ts`. Preserve `APP_NAME` only for metadata, alt text, and document title while removing visible logo-adjacent text from the branded UI surfaces.

**Tech Stack:** Next.js App Router, React 19, Node `node:test`, Markdown README assets

---

### Task 1: Add brand regression coverage and shared asset definitions

**Files:**
- Modify: `controller/web/lib/brand.ts`
- Create: `controller/web/tests-node/brand.test.ts`
- Modify: `controller/web/app/layout.tsx`

- [ ] **Step 1: Write the failing test**

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { BRAND_ICON_SRC, BRAND_LOGO_SRC, buildAppMetadata } from "../lib/brand.ts";

test("exports the shared web brand asset paths", () => {
  assert.equal(BRAND_LOGO_SRC, "/branding/logo.png");
  assert.equal(BRAND_ICON_SRC, "/favicon.ico");
});

test("builds app metadata with favicon wiring", () => {
  const metadata = buildAppMetadata();

  assert.equal(metadata.title, "thirdeye");
  assert.deepEqual(metadata.icons, {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/branding/logo.png",
  });
});
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `node --test tests-node/brand.test.ts`

Expected: FAIL because the brand asset exports and metadata helper do not exist yet.

- [ ] **Step 3: Add the shared brand exports and metadata helper**

```ts
export const APP_NAME = "thirdeye";
export const BRAND_LOGO_SRC = "/branding/logo.png";
export const BRAND_ICON_SRC = "/favicon.ico";

export function buildAppMetadata(): Metadata {
  return {
    title: APP_NAME,
    description: "Operational controller for local-first livestream capture.",
    icons: {
      icon: BRAND_ICON_SRC,
      shortcut: BRAND_ICON_SRC,
      apple: "/branding/logo.png",
    },
  };
}
```

- [ ] **Step 4: Run the targeted test again**

Run: `node --test tests-node/brand.test.ts`

Expected: PASS

### Task 2: Replace branded text surfaces with the shared logo

**Files:**
- Create: `controller/web/components/app-logo.tsx`
- Modify: `controller/web/components/app-header.tsx`
- Modify: `controller/web/components/app-sidebar.tsx`
- Modify: `controller/web/app/login/page.tsx`
- Create: `controller/web/public/branding/logo.png`
- Modify: `controller/web/public/favicon.ico`

- [ ] **Step 1: Build the shared logo component**

```tsx
import Image from "next/image";

import { BRAND_LOGO_ALT, BRAND_LOGO_SRC } from "../lib/brand";

export function AppLogo({ className }: { className?: string }) {
  return (
    <Image
      alt={BRAND_LOGO_ALT}
      className={className}
      height={48}
      priority
      src={BRAND_LOGO_SRC}
      width={192}
    />
  );
}
```

- [ ] **Step 2: Replace text branding with the logo in shared UI surfaces**

```tsx
<div className="min-w-0 flex-1">
  <AppLogo className="h-9 w-auto" />
  <h1 className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-white sm:text-[2rem]">{title}</h1>
</div>
```

- [ ] **Step 3: Copy the provided assets into Next public branding paths**

Run: `mkdir -p controller/web/public/branding && cp assets/logo.png controller/web/public/branding/logo.png && magick assets/favicon.png -define icon:auto-resize=16,32,48,64,128,256 controller/web/public/favicon.ico`

Expected: the app can serve `/branding/logo.png` and `/favicon.ico`.

### Task 3: Update the README and verify the full change

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the text heading with the standalone logo**

```md
<p align="center">
  <img src="assets/logo.png" alt="thirdeye logo" width="280">
</p>
```

- [ ] **Step 2: Run verification**

Run: `cd controller/web && node --test tests-node/brand.test.ts && npm run build`

Expected: PASS and Next production build succeeds with the new metadata and asset usage.
