# Controller Web UI Revamp Design

**Date:** 2026-04-18

**Goal:** Replace the current bespoke controller UI with a shadcn-based design system and a clearer navigation model so operators can move through capture, supervision, and archive tasks with less scanning and fewer context switches.

## Current State

The existing `controller/web` app is visually coherent, but the product structure is still page-by-page rather than workspace-driven.

Current UX issues:

1. The dashboard tries to be landing page, launch form, health board, active-session supervisor, and recent archive all at once.
2. Navigation is repeated in local page headers instead of being anchored in one persistent app shell.
3. There is no dedicated jobs index, so the operator’s primary objects are only reachable indirectly.
4. Job detail and live transcript are split into separate screens even though operators treat them as one workflow.
5. The UI relies on a project-specific styling helper layer in `controller/web/lib/ui.ts`, which makes large-scale redesign work harder to reason about and reuse.

## Approved Direction

The new UI will use a minimalist operational-cockpit aesthetic:

- dark, restrained, status-forward, and high contrast
- minimal chrome, but stronger hierarchy than the current long-form pages
- global navigation and consistent page framing
- shadcn primitives as the base design system
- fewer bespoke UI wrappers and less repeated page scaffolding

This is a structural redesign, not a visual reskin.

## Design

### 1. Information architecture

The app will be reorganized around four durable surfaces:

- `/login` for authenticated entry
- `/` as the operational dashboard for what needs attention now
- `/jobs` as the canonical browse surface for all sessions
- `/jobs/[jobId]` as the single workspace for one session
- `/artifacts` as a secondary file-first surface for audit and download

The current `/jobs/[jobId]/live` route will stop being a primary destination. Its live-transcript content will move into the job workspace. The route can remain as a compatibility redirect to `/jobs/[jobId]`.

### 2. App shell and navigation

The app will get a persistent shell shared by all authenticated routes.

Shell structure:

- compact left rail on desktop and sheet navigation on mobile
- top bar with page title, short contextual description, and session actions
- primary nav items: `Dashboard`, `Jobs`, `Artifacts`
- secondary actions: external `Desktop` link and logout control

The shell should make route changes feel like moving within one application instead of loading independent landing pages.

### 3. Dashboard

The dashboard will become a high-signal operational overview, not a generic catch-all.

Primary regions:

- active capture spotlight with direct entry to the current job workspace
- launch card for starting a new capture
- health stack for desktop, Deepgram, and OpenClaw
- recent priority jobs list focused on active, failed, and recently completed sessions
- compact metrics row for in-flight jobs, completed jobs, and artifact volume

The dashboard should answer:

- what is happening now
- what requires action
- what can I start next

It should not try to replace the dedicated jobs browser.

### 4. Jobs index

`/jobs` will be introduced as the main list view for sessions.

Behavior:

- show all jobs in a scannable list/card hybrid
- surface title, state, timestamps, artifact count, summary availability, and quick actions
- make active and failed jobs visually easier to find
- provide direct entry to the full job workspace

This page replaces the current “recent capture files” section as the main session browser.

### 5. Job workspace

`/jobs/[jobId]` will become the center of gravity for session work.

Layout:

- hero header with title, current state, critical timestamps, and primary actions
- segmented workspace sections or tabs for `Overview`, `Live`, `Artifacts`, and `Timeline`
- transcript summary tooling placed with the job workflow instead of feeling like an isolated panel

Priorities:

- primary actions appear before long metadata blocks
- destructive actions are visually separated from navigation and recovery actions
- live transcript supervision is reachable without leaving the workspace
- dense metadata is grouped into secondary cards instead of dominating the page

### 6. Artifacts page

`/artifacts` stays in the product, but its role becomes narrower and clearer.

It will focus on:

- downloadable files by session
- file names, sizes, and states
- direct links back into the related job workspace

It should feel like an audit/download ledger, not a second jobs page.

### 7. Login experience

The login page will adopt the same visual system as the main app, but remain simpler and quieter.

Requirements:

- clear product identity
- one primary authentication card
- short explanation of what the controller does
- less decorative duplication than the current multi-panel intro

### 8. Design system and shadcn usage

The redesign will introduce shadcn-style UI building blocks under `controller/web/components/ui`.

Expected primitive coverage:

- `Button`
- `Card`
- `Badge`
- `Input`
- `Textarea`
- `Label`
- `Separator`
- `Sheet`
- `Tabs` or segmented navigation equivalent
- `ScrollArea` for long transcript surfaces

The current `lib/ui.ts` file should be retired after replacement. Styling logic that is not purely presentational, such as state-label formatting, should move into a smaller utility module instead of staying in the old UI helper layer.

### 9. Visual direction

The visual system should stay minimalist but intentional:

- strong contrast with muted surfaces and restrained accent color
- typography with a technical/editorial feel, not a generic SaaS look
- fewer oversized hero blocks
- more rhythm from spacing, borders, and section framing
- clear status semantics for active, complete, warning, and neutral states

The app should feel calm and controlled, not decorative.

### 10. Behavior and interaction changes

The redesign should improve task flow without changing the controller’s backend behavior.

Interaction changes:

- operators should always have a fast path from dashboard to the active job workspace
- job actions should be grouped by intent: navigation, operational actions, archive mutations
- live transcript supervision should show stronger connection and capture cues
- empty states should direct the next action instead of just describing absence

Non-UI business logic such as job actions, SSE transcript replay, and summary generation should remain intact unless required to support the new structure.

### 11. Testing strategy

Tests will need to shift from current copy/layout assumptions toward the new IA.

Required updates:

- Playwright coverage for login, dashboard, jobs index, job workspace, and artifacts
- update route expectations so the main capture flow lands in the new workspace model
- preserve transcript-summary and live-transcript behavior coverage
- keep Node tests for non-visual helpers, but relax brittle markup assertions where the redesign intentionally changes structure

### 12. Cleanup strategy

After the new shell and pages are in place, stale UI code should be removed.

Expected cleanup targets:

- `controller/web/lib/ui.ts`
- bespoke styling wrappers that only exist to carry old class strings
- duplicate page-local header scaffolding
- any route-specific UI code replaced by the job workspace model

Cleanup must happen after replacement, not before. Behavior-bearing components should only be deleted once their logic is preserved in the new implementation.

## Files Expected To Change

- `controller/web/package.json`
- `controller/web/package-lock.json`
- `controller/web/app/layout.tsx`
- `controller/web/app/globals.css`
- `controller/web/app/page.tsx`
- `controller/web/app/login/page.tsx`
- `controller/web/app/artifacts/page.tsx`
- `controller/web/app/jobs/[jobId]/page.tsx`
- `controller/web/app/jobs/[jobId]/live/page.tsx`
- `controller/web/components/*`
- `controller/web/components/ui/*`
- `controller/web/lib/ui.ts` or its replacement utilities
- `controller/web/tests/controller.spec.ts`
- any Node-side tests coupled to the current UI structure

Expected new files include at least:

- `controller/web/app/jobs/page.tsx`
- authenticated app-shell components
- shadcn primitives under `controller/web/components/ui`

## Error Handling

The redesign will preserve existing error behavior:

- form submission errors stay inline
- destructive actions remain explicitly gated by current job state
- transcript summary failures remain visible without losing the current page context
- live transcript connection loss remains visible in the workspace, with stronger status language

## Non-Goals

- changing controller API contracts
- redesigning backend job lifecycle behavior
- changing artifact formats
- changing authentication semantics
- adding large new product features unrelated to navigation and UX clarity
