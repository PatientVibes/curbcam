# curbcam — UX / Front-End Design Uplift — Design Spec

- **Date:** 2026-05-29
- **Status:** Approved (design direction confirmed with user)
- **Owner:** PatientVibes
- **Context:** MVP-2 shipped a deliberately function-first UI (server-rendered Jinja + htmx +
  hand-rolled `app.css`). A grounded review (live instance + Playwright screenshots of every screen,
  2026-05-29) confirmed it works but is essentially unstyled — stark black nav, system defaults, no
  design system, no brand. This spec defines a presentation-layer uplift to reach the design spec's
  "OctoPrint-tier polish" goal (`docs/specs/2026-05-28-curbcam-design.md` §2.6).

## 1. Goal

Make curbcam *look and feel* like a polished, trustworthy homelab product — without changing what it
does. A small, hand-authored CSS design system + a restyle of every existing screen, plus a light
brand identity and a few cross-cutting fixes the review surfaced.

## 2. Direction (decided)

- **Aesthetic:** a clean, modern self-hosted-dashboard base (OctoPrint / Uptime-Kuma family — familiar
  to the Pi/homelab audience) with a **distinctive speed-camera identity**: a single "radar" accent
  color and big, confident, tabular speed readouts.
- **Theme:** light **and** dark, defaulting to the OS/browser preference, with a manual toggle.
- **Brand:** a light identity — a `curbcam` wordmark, one named accent color, and a favicon/app icon.
- **Audience bar:** clear over flashy; legible to a non-technical neighbor, credible to a homelabber.

## 3. Scope

### 3.1 In scope
- A hand-authored CSS **design system** (tokens + components) under `web/static/`.
- A **restyle of every existing screen**: app shell/nav, first-run wizard, alignment, calibration,
  dashboard, events, settings (and their partials).
- **Brand:** wordmark, accent, favicon/app icon (also fixes the current `favicon.ico` 404).
- **Cross-cutting fixes surfaced by the review:** the setup live-preview broken image (functional);
  dashboard event-list cap + empty/loading states; an accessibility pass; responsive/mobile.
- A theme toggle (small vanilla JS, persisted).

### 3.2 Non-goals (hard boundaries)
- **No API/route/behavior changes.** This is a pure presentation layer: same endpoints, same htmx
  interactions, same backend. (One exception is explicitly allowed: a minimal, behavior-preserving
  template/JS change to fix the setup live-preview image — see §6.2.)
- **No new pages or flows**; restyle what exists.
- **No SPA, no JS framework, no CSS framework, no build step.** All assets vendored (offline/LAN —
  the device often has no internet).
- No new fonts shipped (use the system font stack); no icon-font dependency (inline SVG only).
- Not a redesign of the detector/algorithm or the wizard's step *logic* — only its presentation.

## 4. Approach (chosen, with rejected alternatives)

A **hand-authored CSS design system** using CSS custom properties for tokens, plain component classes,
and a tiny theme-toggle script. No framework, no build step, all vendored.

- **Rejected — Pico/classless CSS:** faster to a generic look, but adds a dependency and undercuts the
  distinctive speed-cam identity.
- **Rejected — Tailwind:** powerful, but a Node/build pipeline fights the Python+Jinja+htmx simplicity
  and the no-build-step / offline constraint.

## 5. The design system (`web/static/`)

### 5.1 Files
- `static/css/tokens.css` — CSS custom properties: color (light + dark), spacing, radius, type scale,
  shadow/elevation, z-index, transitions.
- `static/css/app.css` — component + layout styles built on the tokens (replaces today's single
  hand-rolled `app.css`).
- `static/js/theme.js` — reads/sets `[data-theme]` on `<html>`, persists to `localStorage`, applied
  before first paint (no flash). Vendored, ~20 lines.
- `static/icons/` — favicon + app icon (SVG + a PNG fallback) and any inline-SVG sources.

(Existing `align.js` / `calibrate.js` keep their behavior; only markup/classes they touch may change.)

### 5.2 Tokens
- **Color:** a neutral surface/elevation ramp (`--surface-0..3`, `--text`, `--text-muted`, `--border`),
  one **accent** (`--accent` "radar" hue + hover/active), and semantics (`--ok`, `--warn`, `--danger`,
  direction L↔R). Both themes defined as variable sets; dark via `prefers-color-scheme` and a
  `[data-theme="dark"]` override.
- **Type:** system UI font stack; a type scale (`--fs-…`); **`font-variant-numeric: tabular-nums`** on
  speed readouts so digits don't jitter as they update.
- **Space/radius/shadow:** small consistent scales (`--space-1..6`, `--radius-…`, `--shadow-…`).

### 5.3 Components (classes, reused across templates)
App shell + top nav (wordmark, links, theme toggle); buttons (`.btn`, `.btn-primary`,
`.btn-danger`); form controls (inputs/selects/checkbox, labels, help text, inline errors); cards;
**event card** (thumbnail · big tabular speed · direction chip · relative time); **status pill**
(idle/tracking · fps); **wizard stepper** (1–5, current/done/upcoming); filter bar; table; empty-state
and loading/skeleton blocks; badges (e.g. the "set via environment" indicator).

## 6. Per-screen restyle

All changes are markup-class + CSS; Jinja structure and htmx attributes preserved unless noted.

### 6.1 App shell & nav (`base.html`)
Replace the stark black bar with a proper header: `curbcam` wordmark + accent, nav links, a theme
toggle. Add `<link rel="icon">` (favicon/app icon) and sensible `<title>`/meta. Consistent page
container + spacing.

### 6.2 First-run wizard (`setup/*.html`)
A real **1–5 stepper** showing progress; one focused step per view; a welcoming first screen (password)
in a centered card; styled consent, camera-source, and links. **Fix the broken live-preview image**
(§3.1): show a framed placeholder until the stream is live, handle the `<img>` error/`onerror`
gracefully, and ensure the preview `<img>` is authorized (it currently renders broken during setup).
This is the one allowed behavior touch — minimal and preserving the existing endpoints.

### 6.3 Calibration & alignment (`setup/calibrate.html`, `setup/align.html`)
Lay the calibration controls in a clear vertical flow instead of one cramped line: capture → **on-frame
guidance** ("click the two ends") with the px readout shown prominently → distance/units/direction →
primary Save. Make the canvas the visual focus; framed reference image with a placeholder before
capture. Alignment: the drag-to-crop gets the same framed-canvas treatment + clear save affordance.

### 6.4 Dashboard (`dashboard.html`, `partials/event_card.html`)
Hero live preview with a prominent **status pill** (idle / **tracking**, fps). Event grid of styled
cards: thumbnail, **big tabular speed numeral**, direction chip, **relative time** ("2 min ago"). Add
an **empty state** ("No events yet — point the camera at the road"), a **loading** state, and **cap the
list** to the last N with a "See all → Events" link (today it grows unbounded). SSE insert keeps
working; new cards animate in subtly.

### 6.5 Events (`events.html`, `partials/events_rows.html`)
A proper **filter bar** (date range, speed range, direction, CSV export) laid out cleanly and wrapping
on mobile; the same styled card grid (or a comfortable table) with pagination and an empty state.

### 6.6 Settings (`settings.html`, `partials/settings_form.html`)
Keep the Primary/Advanced grouping but as styled sections with aligned label/control/help rows; style
the "set via environment" **badge**; **danger styling** on the "delete old events" action (with a
confirm affordance); clear Save/feedback states.

## 7. Cross-cutting

- **Favicon/app icon** — fixes the `favicon.ico` 404; vendored SVG + PNG.
- **Setup live-preview bug** (§6.2) — functional.
- **Dashboard cap + empty/loading states** (§6.4).
- **Accessibility:** real `<label>`s, visible focus rings, AA contrast in both themes, keyboard paths
  for the wizard and calibration, `aria-live` on the SSE event feed and status pill.
- **Responsive:** fluid container, grid → single column on mobile, wrapping filter/nav, tap targets.

## 8. Constraints

Jinja + htmx kept; no SPA/framework/build step; all assets vendored (offline/LAN); presentation-only
(no API/route/behavior change except §6.2); no new pages; system fonts only; inline SVG (no icon
font). Follows existing template/static layout.

## 9. Testing

- **No functional regression:** the existing Playwright e2e calibration smoke must still pass; the
  wizard → calibrate → dashboard → SSE flow works unchanged (re-verifiable against a FileReplaySource
  or a real webcam as in the 2026-05-29 session).
- **Visual once-over:** screenshot each screen in light + dark + a mobile width (Playwright) and
  eyeball against this spec.
- **A11y spot-check:** keyboard-tab the wizard + settings; check focus visibility and contrast.
- **Gates stay green:** ruff / mypy unaffected (no Python logic change); any new JS stays lint-clean.

## 10. Risks

- **Scope creep into behavior.** Mitigation: the §3.2 boundary — only §6.2 may touch behavior.
- **Theming flash / contrast bugs.** Mitigation: apply `[data-theme]` before first paint; test both
  themes for AA contrast.
- **Subjectivity / iteration cost on the accent + brand.** Mitigation: a single tunable `--accent`
  token; the wordmark/icon are simple and swappable.
- **htmx-swapped partials losing styles.** Mitigation: style via classes present in the partial
  templates themselves (event card, events rows), not just page-level wrappers.

## 11. Open questions

None at design time. The exact accent hue and wordmark treatment are tunable during implementation via
the single `--accent` token and a small wordmark partial.
