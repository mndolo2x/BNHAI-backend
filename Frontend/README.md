# Botswana National Healthcare AI Platform

A monochrome, desktop-first clinical operations frontend prototype built with Next.js, React, TypeScript, Tailwind CSS, and Lucide React. All records are synthetic and all actions are local prototype interactions; no clinical system, AI service, identity provider, or backend is connected.

## Run locally

```bash
pnpm install
pnpm dev
```

Open `http://localhost:3000` in a browser. To create a production build:

```bash
pnpm build
pnpm start
```

## Included workflows

- Dashboard metric navigation, assigned work, recent activity, and quick actions
- Searchable patient directory with patient workspace, timeline, source references, and follow-up summary
- Laboratory result review queue with search and status filtering
- Follow-up queue with simulated status transitions
- Encounter overview with contextual Clinical Copilot drawer and explicit AI draft labeling
- Notifications, audit, administration, reports, settings, and integration prototype states
- Responsive sidebar and table layouts for tablet and narrow screens

## Structure

- `app/page.tsx` — interactive application shell, typed synthetic records, page views, and prototype state
- `app/globals.css` — strict black-and-white visual system and responsive layout
- `app/layout.tsx` — metadata, viewport, and application root
- `components/ui/` — reusable shadcn-compatible primitives

The synthetic data and UI state are intentionally kept behind the page-level prototype service boundary so they can later be replaced by FastAPI requests without changing the product shell.
