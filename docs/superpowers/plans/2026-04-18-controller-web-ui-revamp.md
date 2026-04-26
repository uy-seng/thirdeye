# Controller Web UI Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `controller/web` into a shadcn-based operational workspace with a persistent app shell, a dedicated jobs index, a unified job workspace, and removal of obsolete bespoke UI code.

**Architecture:** Keep all existing controller API contracts and client-side behaviors, but move the presentation layer onto reusable shadcn primitives and an authenticated shell. The route model changes from page-local hero layouts to a global workspace model where `/` is an overview, `/jobs` is the canonical browse surface, and `/jobs/[jobId]` absorbs the live transcript into one session workspace.

**Tech Stack:** Next.js App Router, React 19, Tailwind CSS v4, shadcn-style component primitives, Playwright, existing Node-side tests

---

### Task 1: Lay the shadcn foundation and shared app shell

**Files:**
- Modify: `controller/web/package.json`
- Modify: `controller/web/package-lock.json`
- Modify: `controller/web/app/layout.tsx`
- Modify: `controller/web/app/globals.css`
- Create: `controller/web/lib/utils.ts`
- Create: `controller/web/lib/job-state.ts`
- Create: `controller/web/components/ui/button.tsx`
- Create: `controller/web/components/ui/card.tsx`
- Create: `controller/web/components/ui/badge.tsx`
- Create: `controller/web/components/ui/input.tsx`
- Create: `controller/web/components/ui/textarea.tsx`
- Create: `controller/web/components/ui/label.tsx`
- Create: `controller/web/components/ui/separator.tsx`
- Create: `controller/web/components/ui/sheet.tsx`
- Create: `controller/web/components/ui/tabs.tsx`
- Create: `controller/web/components/ui/scroll-area.tsx`
- Create: `controller/web/components/app-shell.tsx`
- Create: `controller/web/components/app-sidebar.tsx`
- Create: `controller/web/components/app-header.tsx`
- Test: `controller/web/tests/controller.spec.ts`

- [ ] **Step 1: Write the failing UI-shell expectations in Playwright**

```ts
test("authenticated routes render inside the shared workspace shell", async ({ page }) => {
  await authenticate(page);

  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Jobs" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Artifacts" })).toBeVisible();
});
```

- [ ] **Step 2: Run the targeted Playwright test to verify it fails**

Run: `npm run test:e2e -- --grep "shared workspace shell"`

Expected: FAIL because the current app has page-local headers and no shared primary navigation.

- [ ] **Step 3: Add the shadcn runtime dependencies**

```bash
npm install @radix-ui/react-dialog @radix-ui/react-label @radix-ui/react-scroll-area @radix-ui/react-separator @radix-ui/react-slot @radix-ui/react-tabs class-variance-authority clsx lucide-react tailwind-merge
```

- [ ] **Step 4: Add shared utility helpers for class merging and job-state formatting**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatStateLabel(state: string) {
  return state.replaceAll("_", " ");
}
```

- [ ] **Step 5: Implement shadcn primitives and the authenticated shell**

```tsx
export function AppShell({ title, description, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-[var(--app-bg)] text-[var(--app-fg)]">
      <div className="mx-auto grid min-h-screen max-w-[1600px] grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)]">
        <AppSidebar />
        <div className="flex min-w-0 flex-col">
          <AppHeader description={description} title={title} />
          <main className="flex-1 px-4 pb-6 pt-4 sm:px-6 lg:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Rebuild global styling around app tokens instead of `lib/ui.ts`**

```css
@theme {
  --color-canvas: #07111a;
  --color-panel: rgba(9, 18, 28, 0.78);
  --color-line: rgba(148, 163, 184, 0.14);
  --color-accent: #7dd3fc;
}
```

- [ ] **Step 7: Run the targeted shell Playwright test again**

Run: `npm run test:e2e -- --grep "shared workspace shell"`

Expected: PASS

### Task 2: Rebuild the route model around dashboard, jobs index, and artifacts

**Files:**
- Modify: `controller/web/app/page.tsx`
- Create: `controller/web/app/jobs/page.tsx`
- Modify: `controller/web/app/artifacts/page.tsx`
- Modify: `controller/web/components/start-capture-form.tsx`
- Create: `controller/web/components/dashboard-active-job.tsx`
- Create: `controller/web/components/dashboard-metrics.tsx`
- Create: `controller/web/components/jobs-list.tsx`
- Create: `controller/web/components/jobs-list-row.tsx`
- Create: `controller/web/components/artifact-list.tsx`
- Create: `controller/web/components/health-status-grid.tsx`
- Modify: `controller/web/components/health-card.tsx`
- Modify: `controller/web/components/status-badge.tsx`
- Test: `controller/web/tests/controller.spec.ts`

- [ ] **Step 1: Write failing tests for the new top-level IA**

```ts
test("dashboard focuses on active work while jobs owns browsing", async ({ page }) => {
  await authenticate(page);

  await expect(page.getByRole("heading", { name: "Operations overview" })).toBeVisible();
  await page.getByRole("link", { name: "Jobs" }).click();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.getByRole("heading", { name: "All sessions" })).toBeVisible();
});
```

- [ ] **Step 2: Run the IA Playwright test to verify it fails**

Run: `npm run test:e2e -- --grep "dashboard focuses on active work"`

Expected: FAIL because `/jobs` does not exist and the dashboard still owns archive browsing.

- [ ] **Step 3: Replace the dashboard with an operations-first layout**

```tsx
<AppShell description="What needs attention now" title="Operations overview">
  <DashboardMetrics
    artifactCount={artifactCount}
    completedCount={readyCount}
    inFlightCount={activeCount}
  />
  <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_380px]">
    <DashboardActiveJob active={active} />
    <StartCaptureForm />
  </div>
  <HealthStatusGrid health={health} />
  <JobsList items={priorityJobs} title="Priority queue" />
</AppShell>
```

- [ ] **Step 4: Add the canonical jobs index**

```tsx
<AppShell description="Browse every capture session" title="All sessions">
  <JobsList items={overview.jobs} title="Session ledger" />
</AppShell>
```

- [ ] **Step 5: Narrow the artifacts page into a file-first ledger**

```tsx
<AppShell description="Download generated files by session" title="Artifacts">
  <ArtifactList entries={overview.jobs} />
</AppShell>
```

- [ ] **Step 6: Refactor shared list/status components onto the new primitives**

```tsx
<Card>
  <CardHeader>
    <div className="flex items-center justify-between gap-3">
      <Link href={`/jobs/${job.id}`}>{job.title}</Link>
      <StatusBadge state={job.state} />
    </div>
  </CardHeader>
</Card>
```

- [ ] **Step 7: Run the IA-focused Playwright tests again**

Run: `npm run test:e2e -- --grep "dashboard focuses on active work|authenticate into the dashboard"`

Expected: PASS

### Task 3: Turn the job detail page into a single workspace and preserve live behavior

**Files:**
- Modify: `controller/web/app/jobs/[jobId]/page.tsx`
- Modify: `controller/web/app/jobs/[jobId]/live/page.tsx`
- Modify: `controller/web/components/job-actions.tsx`
- Modify: `controller/web/components/live-transcript-stream.tsx`
- Modify: `controller/web/components/transcript-summary-panel.tsx`
- Create: `controller/web/components/job-workspace.tsx`
- Create: `controller/web/components/job-overview-panel.tsx`
- Create: `controller/web/components/job-metadata-panel.tsx`
- Create: `controller/web/components/job-artifacts-panel.tsx`
- Create: `controller/web/components/job-timeline-panel.tsx`
- Test: `controller/web/tests/controller.spec.ts`
- Test: `controller/web/tests-node/live-transcript.test.ts`

- [ ] **Step 1: Write failing tests for the unified workspace**

```ts
test("job workspace keeps live transcript inside the session page", async ({ page }) => {
  await authenticate(page);
  const jobId = await createCompletedJob(page, `Workspace ${Date.now()}`);

  await page.goto(`/jobs/${jobId}`);
  await expect(page.getByRole("tab", { name: "Live" })).toBeVisible();
  await page.getByRole("tab", { name: "Live" }).click();
  await expect(page.getByTestId("live-transcript-board")).toBeVisible();
});
```

- [ ] **Step 2: Run the workspace Playwright and Node tests to verify they fail**

Run: `npm run test:e2e -- --grep "job workspace keeps live transcript"`

Run: `node --test tests-node/live-transcript.test.ts`

Expected: FAIL because live transcript still lives on `/jobs/[jobId]/live` and markup assumptions have not been updated.

- [ ] **Step 3: Replace the current job page with a tabbed workspace**

```tsx
<AppShell description="Session workspace" title={job.title}>
  <JobWorkspace
    artifacts={artifacts.files}
    defaultTab="overview"
    job={job}
  />
</AppShell>
```

- [ ] **Step 4: Fold live transcript, timeline, artifacts, and summary tooling into workspace panels**

```tsx
<Tabs defaultValue="overview">
  <TabsList>
    <TabsTrigger value="overview">Overview</TabsTrigger>
    <TabsTrigger value="live">Live</TabsTrigger>
    <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
    <TabsTrigger value="timeline">Timeline</TabsTrigger>
  </TabsList>
</Tabs>
```

- [ ] **Step 5: Re-group job actions by intent and isolate destructive actions**

```tsx
<div className="grid gap-3 lg:grid-cols-2">
  <Card>Navigation and monitoring actions</Card>
  <Card>Operational recovery actions</Card>
  <Card className="border-rose-500/20">Archive mutation actions</Card>
</div>
```

- [ ] **Step 6: Convert `/jobs/[jobId]/live` into a compatibility redirect**

```tsx
import { redirect } from "next/navigation";

export default async function LivePage({ params }: Props) {
  const { jobId } = await params;
  redirect(`/jobs/${jobId}?tab=live`);
}
```

- [ ] **Step 7: Update transcript tests to assert behavior instead of old structure**

```ts
assert.match(source, /data-testid="live-transcript-board"/);
assert.match(source, /Awaiting speech|Speech detected|Capture complete/);
```

- [ ] **Step 8: Run workspace and transcript tests again**

Run: `npm run test:e2e -- --grep "job workspace keeps live transcript|job page can generate and save a transcript summary prompt"`

Run: `node --test tests-node/live-transcript.test.ts`

Expected: PASS

### Task 4: Rebuild login/forms, remove stale UI glue, and verify the full app

**Files:**
- Modify: `controller/web/app/login/page.tsx`
- Modify: `controller/web/components/login-form.tsx`
- Modify: `controller/web/components/logout-button.tsx`
- Delete: `controller/web/lib/ui.ts`
- Delete: `controller/web/components/job-card.tsx`
- Modify: `controller/web/tests/controller.spec.ts`
- Modify: `controller/web/tests-node/health-card.test.ts`
- Modify: `controller/web/tests-node/job-action-status.test.ts`

- [ ] **Step 1: Write failing tests for the refreshed login and final cleanup**

```ts
test("login screen matches the workspace visual system", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "thirdeye" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Enter Control Room" })).toBeVisible();
  await expect(page.getByText("Local-first capture control")).toBeVisible();
});
```

- [ ] **Step 2: Run the login-focused test to verify it fails**

Run: `npm run test:e2e -- --grep "login screen matches the workspace visual system"`

Expected: FAIL because the login page still uses the old intro framing and copy.

- [ ] **Step 3: Rebuild the login page and forms on top of shadcn inputs/buttons**

```tsx
<Card className="mx-auto w-full max-w-md">
  <CardHeader>
    <CardTitle>thirdeye</CardTitle>
    <CardDescription>Local-first capture control</CardDescription>
  </CardHeader>
  <CardContent>
    <LoginForm />
  </CardContent>
</Card>
```

- [ ] **Step 4: Remove stale UI glue and unused wrappers**

```ts
// delete controller/web/lib/ui.ts after all imports move to:
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
```

- [ ] **Step 5: Run static cleanup checks**

Run: `rg -n "lib/ui" controller/web`

Expected: no matches

- [ ] **Step 6: Run the full verification suite**

Run: `npm run build`

Run: `node --test tests-node/*.test.ts`

Run: `npm run test:e2e`

Expected: all commands exit 0
