# curbcam — UX / Front-End Design Uplift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle every curbcam web screen to a polished "homelab-dashboard + speed-cam identity" look (light/dark, brand wordmark, big tabular speeds) via a hand-authored CSS design system — with **zero server/API/behavior change** and **no broken JS hooks**.

**Architecture:** Pure presentation layer. A token-driven `app.css` (CSS custom properties; light + `[data-theme="dark"]`), a blocking inline theme-init in `<head>` (no FOUC), a restyled shell/nav + wordmark + favicon, and per-screen restyles. The client JS that *builds/themes* DOM is in scope: the SSE event-card builder in `app.js` is refactored to stay byte-identical to the restyled `event_card.html` partial, and the calibration/alignment canvas colors read CSS variables. Jinja + htmx kept; no framework, no build step, all assets vendored.

**Tech Stack:** HTML/Jinja2, vanilla CSS (custom properties), vanilla JS, htmx (vendored, unchanged). No Node/build. Verification via `curbcam serve` + Playwright screenshots and the existing e2e calibration smoke.

**Reference:** Spec at `docs/specs/2026-05-29-curbcam-ux-uplift.md` (cited §N) — read **§5.4 (load-bearing JS hooks) before touching any template**. Plan style: `docs/plans/2026-05-29-curbcam-mvp-3-docker-install.md`.

---

## Ground rules (apply to EVERY task)

1. **Never rename a §5.4 hook.** Preserve these exactly (style them freely, don't rename):
   - ids: `#frame #cal-canvas #pixel-distance #result #capture #undo #reset #submit #distance #units #direction` · `#align-frame #align-canvas #align-result #overlay-toggle #save-crop` · `#event-list` (+`data-sse`,`data-units`) · `#tracking-pill` (+`.active`) · `#preview` · `#rows` · `#settings-form` · `#token-list` · `#camera-result` · `#setup-preview` · **`#setup-step`** (htmx swap unit shared by `password.html` form ↔ `configure.html` div — see §wizard note)
   - **htmx swap-unit rule (`#setup-step`):** `password.html` is `<form id="setup-step" hx-post="/api/setup/password" hx-target="#setup-step" hx-swap="outerHTML">`; on submit it's replaced by `configure.html`'s `<div id="setup-step">`. **Everything for the password step (stepper, welcome card, input, submit) MUST live INSIDE `#setup-step`** — anything outside it persists on screen after the swap (→ a stale/duplicate stepper). Keep the form id, `hx-post`, `hx-target`, `hx-swap`, and the `<input type="password" name="password" required minlength="6">` verbatim.
   - classes JS queries: `form.filters`, `a.csv`, `.event-card .event-meta .speed .dir`, `.load-more`
   - elements: `<time datetime="…">` (filled by `app.js`)
   - htmx target ids referenced by `hx-target` in the same templates (`#rows #settings-form #token-list #camera-result`) — if renamed, rename both ends.
2. **The event card has two render paths** (`partials/event_card.html` + the `app.js` SSE builder). Any change to one MUST be mirrored in the other (Task 4 makes them identical).
3. **No change to fetch URLs, request/response shapes, routes, or Python.** `ruff`/`mypy` must stay untouched-and-green.
4. After each slice: run the app and eyeball the touched screens in **light AND dark**; the e2e smoke must stay green (it actively clicks the calibration canvas).

**Running the app for visual checks** (no camera needed — file-replay):
```bash
cd D:/curbcam
mkdir -p _ux/frames _ux/data _ux/media
uv run --no-sync python -c "import cv2,numpy as np;[cv2.imwrite(f'_ux/frames/f{i:03d}.jpg',cv2.rectangle(np.full((480,640,3),40,np.uint8),(40+i*14,205),(112+i*14,255),(235,235,235),-1)) for i in range(40)]"
CURBCAM_CAMERA__SOURCE=file:./_ux/frames uv run --no-sync curbcam serve --no-mdns --port 8000 \
  --data-dir ./_ux/data --media-dir ./_ux/media --config ./_ux/curbcam.yaml
# In another shell, seed a calibration so the dashboard/events render with data:
uv run --no-sync curbcam calibrate --mm-per-px-l2r 40 --mm-per-px-r2l 40 --reference-distance-mm 2000 --data-dir ./_ux/data
```
(`_ux/` is throwaway — add to `.gitignore` in Task 1 or `rm -rf _ux` when done.)

---

## File map

```
src/curbcam/web/
├── static/
│   ├── app.css                 # MODIFY (rewrite): tokens block + components (single file)
│   ├── app.js                  # MODIFY: theme toggle handler + refactor SSE card builder to match partial
│   ├── calibrate.js            # MODIFY: read canvas colors from CSS vars (no hardcoded "red")
│   ├── align.js                # MODIFY: read canvas colors from CSS vars (no hardcoded "lime")
│   └── favicon.svg             # CREATE (brand mark; fixes /favicon.ico 404)
└── templates/
    ├── base.html               # MODIFY: head (favicon, blocking theme-init, meta), nav (wordmark + theme toggle), main container
    ├── dashboard.html          # MODIFY: hero preview + pill, event grid, empty state, cap
    ├── events.html             # MODIFY: filter bar layout, empty state
    ├── settings.html           # MODIFY: section styling, danger styling
    ├── partials/
    │   ├── event_card.html     # MODIFY: restyled card markup (mirror in app.js)
    │   ├── events_rows.html    # MODIFY: empty state + load-more styling (structure preserved)
    │   └── settings_form.html  # MODIFY: field row layout, env badge, save feedback
    └── setup/
        ├── index.html          # MODIFY: welcome + password card + stepper
        ├── password.html       # MODIFY (if present/used): same card treatment
        ├── configure.html      # MODIFY: stepper steps 2–5, preview onerror/retry
        ├── align.html          # MODIFY: framed canvas, save affordance
        └── calibrate.html      # MODIFY: vertical flow, on-frame guidance
```
No Python files change.

---

## Slice A — Design-system foundation + shell (Tasks 1–2)

### Task 1: Tokens, theme system, favicon, gitignore

**Files:** Modify `src/curbcam/web/static/app.css`, `src/curbcam/web/templates/base.html`, `src/curbcam/web/static/app.js`, `.gitignore`; Create `src/curbcam/web/static/favicon.svg`.

- [ ] **Step 1: Add `_ux/` to `.gitignore`**

Append a line to `.gitignore`:
```gitignore
_ux/
```

- [ ] **Step 2: Rewrite `app.css` with a tokens block + base/shell styles**

Replace the contents of `src/curbcam/web/static/app.css` with the following (component styles for cards/forms/etc. are added in later tasks; this establishes tokens, reset, shell, nav, and keeps the existing `.canvas-wrap` overlay rule intact):

```css
/* ── Design tokens ───────────────────────────────────────────── */
:root {
  /* surfaces & text (light) */
  --surface-0:#f6f7f9; --surface-1:#fff; --surface-2:#eef1f4; --surface-3:#e3e7ec;
  --text:#16191d; --text-muted:#5b636e; --border:#d6dbe1;
  /* brand "radar" accent */
  --accent:#0a7d5a; --accent-hover:#0c9069; --on-accent:#fff;
  /* semantics */
  --ok:#1a7f37; --warn:#b7791f; --danger:#c2410c; --danger-bg:#fff1ec;
  --dir:#0a6cff;
  /* type */
  --font: system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  --fs-0:.8rem; --fs-1:.9rem; --fs-2:1rem; --fs-3:1.25rem; --fs-4:1.6rem; --fs-speed:2rem;
  /* space / radius / shadow / motion */
  --sp-1:.25rem; --sp-2:.5rem; --sp-3:.75rem; --sp-4:1rem; --sp-5:1.5rem; --sp-6:2rem;
  --radius:10px; --radius-pill:999px;
  --shadow:0 1px 2px rgba(16,25,40,.06),0 2px 8px rgba(16,25,40,.08);
  --tr:.15s ease;
}
:root[data-theme="dark"]{
  --surface-0:#0f1216; --surface-1:#161a20; --surface-2:#1d222a; --surface-3:#262d37;
  --text:#e7ebf0; --text-muted:#9aa4b1; --border:#2a313b;
  --accent:#1fb888; --accent-hover:#27d29c; --on-accent:#06231a;
  --danger:#f0743f; --danger-bg:#2a1812; --dir:#5aa2ff;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 2px 10px rgba(0,0,0,.45);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --surface-0:#0f1216; --surface-1:#161a20; --surface-2:#1d222a; --surface-3:#262d37;
    --text:#e7ebf0; --text-muted:#9aa4b1; --border:#2a313b;
    --accent:#1fb888; --accent-hover:#27d29c; --on-accent:#06231a;
    --danger:#f0743f; --danger-bg:#2a1812; --dir:#5aa2ff;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 2px 10px rgba(0,0,0,.45);
  }
}

/* ── Base ────────────────────────────────────────────────────── */
*{box-sizing:border-box}
body{margin:0;font-family:var(--font);color:var(--text);background:var(--surface-0);font-size:var(--fs-2);line-height:1.5}
h1{font-size:var(--fs-4);margin:0 0 var(--sp-4)} h2{font-size:var(--fs-3);margin:var(--sp-5) 0 var(--sp-3)}
a{color:var(--accent)}

/* ── App shell + nav ─────────────────────────────────────────── */
.nav{display:flex;align-items:center;gap:var(--sp-4);padding:var(--sp-3) var(--sp-4);
  background:var(--surface-1);border-bottom:1px solid var(--border)}
.nav .brand{font-weight:700;letter-spacing:-.01em;color:var(--text);text-decoration:none;display:flex;align-items:center;gap:var(--sp-2)}
.nav .brand .dot{width:.6rem;height:.6rem;border-radius:50%;background:var(--accent)}
.nav a:not(.brand){color:var(--text-muted);text-decoration:none;padding:var(--sp-1) var(--sp-2);border-radius:6px}
.nav a:not(.brand):hover{color:var(--text);background:var(--surface-2)}
.nav .spacer{margin-left:auto}
.theme-toggle{background:var(--surface-2);border:1px solid var(--border);color:var(--text);
  border-radius:var(--radius-pill);padding:var(--sp-1) var(--sp-3);cursor:pointer;font-size:var(--fs-1)}
.main{padding:var(--sp-5) var(--sp-4);max-width:1040px;margin:0 auto}

/* ── Canvas overlay (calibrate/align) — keep exactly (spec §5.4) ─ */
.canvas-wrap{position:relative;display:inline-block;max-width:640px}
.canvas-wrap img{display:block;width:100%;border-radius:var(--radius)}
.canvas-wrap canvas{position:absolute;top:0;left:0;cursor:crosshair}
```

- [ ] **Step 3: Add favicon `src/curbcam/web/static/favicon.svg`**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="7" fill="#0a7d5a"/>
  <circle cx="16" cy="16" r="8" fill="none" stroke="#fff" stroke-width="2.5"/>
  <circle cx="16" cy="16" r="2.5" fill="#fff"/>
</svg>
```

- [ ] **Step 4: Update `base.html` head + nav**

Rewrite `src/curbcam/web/templates/base.html` to add the favicon link, the **blocking inline theme-init** (before paint — must NOT be deferred, spec §5.1), and a nav with wordmark + theme toggle. Keep `app.css`/htmx/`app.js` exactly as-is otherwise:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>curbcam{% block title %}{% endblock %}</title>
  <link rel="icon" href="/static/favicon.svg">
  <link rel="stylesheet" href="/static/app.css">
  <script>
    /* Blocking, pre-paint: set theme from saved choice (falls back to OS pref). */
    (function(){try{var t=localStorage.getItem("curbcam-theme");
      if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t);}catch(e){}})();
  </script>
  <script src="/static/vendor/htmx.min.js" defer></script>
  <script src="/static/app.js" defer></script>
</head>
<body>
  <nav class="nav">
    <a href="/" class="brand"><span class="dot"></span>curbcam</a>
    <a href="/">Dashboard</a>
    <a href="/events">Events</a>
    <a href="/settings">Settings</a>
    <span class="spacer"></span>
    <button type="button" class="theme-toggle" id="theme-toggle" aria-label="Toggle light/dark theme">◑</button>
  </nav>
  <main class="main">{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 5: Add the theme-toggle handler to `app.js`**

At the **top** of the `DOMContentLoaded` callback in `src/curbcam/web/static/app.js` (right after `renderTimes(document);`), add:

```javascript
  // Theme toggle: cycle saved theme; blocking head script applies it on load.
  const themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme")
        || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("curbcam-theme", next); } catch (e) {}
    });
  }
```

- [ ] **Step 6: Verify**

Start the app (see "Running the app" above), then:
```bash
# pages still load, favicon resolves (no 404), no Python regressions
curl -s -o /dev/null -w "css %{http_code}\n" http://localhost:8000/static/app.css
curl -s -o /dev/null -w "favicon %{http_code}\n" http://localhost:8000/static/favicon.svg
uv run --no-sync ruff check . && uv run --no-sync mypy src/curbcam
```
Expected: `css 200`, `favicon 200`, ruff/mypy clean. In a browser (or Playwright): the new nav shows the wordmark + toggle; clicking the toggle flips light/dark with no flash; reload preserves the choice.

- [ ] **Step 7: Commit**
```bash
git add src/curbcam/web/static/app.css src/curbcam/web/static/app.js src/curbcam/web/static/favicon.svg src/curbcam/web/templates/base.html .gitignore
git commit -m "feat(ux): design tokens, light/dark theme system, brand nav + favicon"
```

---

### Task 2: Shared component styles (buttons, forms, cards, pill, badges, states)

**Files:** Modify `src/curbcam/web/static/app.css` (append a components section).

- [ ] **Step 1: Append component styles to `app.css`**

These classes are used by every screen in Slices B–D. Append to `src/curbcam/web/static/app.css`:

```css
/* ── Buttons ─────────────────────────────────────────────────── */
button,.btn{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--border);
  background:var(--surface-2);color:var(--text);padding:var(--sp-2) var(--sp-4);transition:background var(--tr)}
button:hover,.btn:hover{background:var(--surface-3)}
.btn-primary,button[type="submit"]{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.btn-primary:hover,button[type="submit"]:hover{background:var(--accent-hover)}
.btn-danger{background:var(--danger);border-color:var(--danger);color:#fff}

/* ── Form controls ───────────────────────────────────────────── */
input,select{font:inherit;color:var(--text);background:var(--surface-1);border:1px solid var(--border);
  border-radius:8px;padding:var(--sp-2) var(--sp-3)}
input:focus,select:focus,button:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
label{color:var(--text)} small.help{display:block;color:var(--text-muted);font-size:var(--fs-1)}
.field-error{color:var(--danger);font-size:var(--fs-1)}
.badge-env{background:var(--surface-3);color:var(--text-muted);font-size:var(--fs-0);
  padding:1px 8px;border-radius:6px;border:1px solid var(--border)}

/* ── Card ────────────────────────────────────────────────────── */
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:var(--sp-5)}

/* ── Status pill ─────────────────────────────────────────────── */
.pill{position:absolute;top:var(--sp-2);left:var(--sp-2);background:rgba(0,0,0,.6);color:#fff;
  padding:2px 10px;border-radius:var(--radius-pill);font-size:var(--fs-0);backdrop-filter:blur(4px)}
.pill.active{background:var(--accent);color:var(--on-accent)}

/* ── Event grid + card ───────────────────────────────────────── */
.event-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:var(--sp-4);margin-top:var(--sp-5)}
.event-card{background:var(--surface-1);border:1px solid var(--border);border-radius:var(--radius);
  overflow:hidden;box-shadow:var(--shadow)}
.event-card img{width:100%;display:block;aspect-ratio:4/3;object-fit:cover;background:var(--surface-3)}
.event-meta{display:flex;align-items:baseline;gap:var(--sp-2);padding:var(--sp-3)}
.event-meta .speed{font-size:var(--fs-speed);font-weight:700;font-variant-numeric:tabular-nums;line-height:1}
.event-meta .dir{color:var(--dir);font-weight:700}
.event-meta time{margin-left:auto;color:var(--text-muted);font-size:var(--fs-1)}

/* ── Empty / loading states ──────────────────────────────────── */
.empty{color:var(--text-muted);text-align:center;padding:var(--sp-6);border:1px dashed var(--border);border-radius:var(--radius)}
.load-more{display:block;margin:var(--sp-4) auto 0}
```

- [ ] **Step 2: Verify**

Reload any page (e.g. `/settings`) and confirm buttons/inputs now pick up the styles; toggle light/dark and confirm contrast on buttons, inputs, badges. `uv run --no-sync ruff check .` (CSS isn't linted, but confirms nothing else broke).

- [ ] **Step 3: Commit**
```bash
git add src/curbcam/web/static/app.css
git commit -m "feat(ux): shared component styles (buttons, forms, cards, pill, event grid, states)"
```

---

## Slice B — Dashboard + the two-path event card (Tasks 3–4)

### Task 3: Restyle the event-card partial

**Files:** Modify `src/curbcam/web/templates/partials/event_card.html`.

- [ ] **Step 1: Update the partial markup**

Keep the load-bearing classes (`.event-card .event-meta .speed .dir`), the `<time datetime>` element, and `data-event-id`. Restyle structure stays the same so the CSS in Task 2 applies; add a direction `aria-label` for a11y:

```html
<article class="event-card" data-event-id="{{ e.id }}">
  <a href="/media/{{ e.image_path }}" target="_blank" rel="noopener">
    <img src="/media/{{ e.thumb_path }}" alt="event {{ e.id }}" loading="lazy">
  </a>
  <div class="event-meta">
    <span class="speed">{{ e.speed_kph | speed(units) }}</span>
    <span class="dir" aria-label="{{ 'left to right' if e.direction == 'L2R' else 'right to left' }}">{{ ">>" if e.direction == "L2R" else "<<" }}</span>
    <time datetime="{{ e.ts_utc.isoformat() }}Z" class="ts"></time>
  </div>
</article>
```

- [ ] **Step 2: Commit** (verified together with Task 4 — they must match)
```bash
git add src/curbcam/web/templates/partials/event_card.html
git commit -m "feat(ux): restyle event-card partial (classes/time preserved)"
```

---

### Task 4: Refactor the `app.js` SSE card builder to MATCH the partial (CRITICAL — spec §5.4)

**Files:** Modify `src/curbcam/web/static/app.js`.

- [ ] **Step 1: Replace the SSE card-building block**

In `src/curbcam/web/static/app.js`, the `es.addEventListener("event", …)` handler builds a card via `createElement`. Replace the card-construction body so it is **structurally identical** to `event_card.html` (adds the missing `data-event-id`, `rel="noopener"`, the `aria-label` on `.dir`, and `class="ts"` on `<time>`):

```javascript
    es.addEventListener("event", (m) => {
      const ev = JSON.parse(m.data);
      const speed = units === "mph"
        ? (ev.speed_kph / 1.609344).toFixed(1)
        : ev.speed_kph.toFixed(1);
      const l2r = ev.direction === "L2R";

      const card = document.createElement("article");
      card.className = "event-card";
      card.dataset.eventId = ev.id;

      const link = document.createElement("a");
      link.href = `/media/${ev.image_path}`;
      link.target = "_blank";
      link.rel = "noopener";
      const img = document.createElement("img");
      img.src = `/media/${ev.thumb_path}`;
      img.alt = `event ${ev.id}`;
      img.loading = "lazy";
      link.appendChild(img);

      const meta = document.createElement("div");
      meta.className = "event-meta";
      const speedEl = document.createElement("span");
      speedEl.className = "speed";
      speedEl.textContent = `${speed} ${units}`;
      const dirEl = document.createElement("span");
      dirEl.className = "dir";
      dirEl.setAttribute("aria-label", l2r ? "left to right" : "right to left");
      dirEl.textContent = l2r ? ">>" : "<<";
      const timeEl = document.createElement("time");
      timeEl.className = "ts";
      timeEl.setAttribute("datetime", `${ev.ts_utc}Z`);
      meta.append(speedEl, dirEl, timeEl);

      card.append(link, meta);
      list.prepend(card);
      renderTimes(card);
      // Keep the dashboard list from growing unbounded (spec §6.4).
      const cap = parseInt(list.dataset.cap || "0", 10);
      if (cap > 0) while (list.children.length > cap) list.lastElementChild.remove();
    });
```

- [ ] **Step 2: Verify SSE card parity (the key check)**

Run the app with the file-replay feed (generates motion → events) + a seeded calibration. Open `/` and watch a live event arrive via SSE; compare it to a server-rendered card after reload. They must be **visually identical**. Concretely, in the browser console on `/`:
```js
document.querySelectorAll('.event-card')[0].outerHTML === document.querySelectorAll('.event-card')[1].outerHTML
```
should differ only by the per-event id/paths/values, not by structure/classes. Confirm in light + dark.

- [ ] **Step 3: Commit**
```bash
git add src/curbcam/web/static/app.js
git commit -m "fix(ux): SSE event-card builder matches restyled partial (two-path sync)"
```

---

### Task 5: Restyle the dashboard (hero preview, pill, empty state, cap)

**Files:** Modify `src/curbcam/web/templates/dashboard.html`.

- [ ] **Step 1: Update `dashboard.html`**

Keep `#preview`, `#tracking-pill.pill`, `#event-list.event-list` + `data-sse`/`data-units`. Wrap the preview in a styled section, add a `data-cap`, a heading, and an empty state:

```html
{% extends "base.html" %}
{% block title %} · Dashboard{% endblock %}
{% block content %}
<section class="preview card" style="padding:0;overflow:hidden;position:relative;max-width:720px">
  <img id="preview" src="/api/stream.mjpeg" alt="live preview" style="display:block;width:100%;background:#000">
  <span id="tracking-pill" class="pill">idle</span>
</section>
<h2>Recent events</h2>
<section id="event-list" class="event-list" data-sse="/api/events/stream" data-units="{{ units }}" data-cap="24">
  {% for e in events %}
    {% include "partials/event_card.html" %}
  {% else %}
    <p class="empty">No events yet — point the camera at the road and they'll appear here live.</p>
  {% endfor %}
</section>
{% endblock %}
```
(The `{% else %}` on the `for` renders only when there are zero events; once SSE inserts a card the empty `<p>` remains but is harmless — acceptable for v1. If you prefer it removed on first insert, that's a NIT, skip for now.)

- [ ] **Step 2: Verify**

On `/`: hero preview shows the feed with the status pill (toggles "tracking"/"idle · N fps" — confirm by watching during motion); event grid is styled with big tabular speeds; with a fresh DB (no events) the empty state shows. Check light + dark.

- [ ] **Step 3: Commit**
```bash
git add src/curbcam/web/templates/dashboard.html
git commit -m "feat(ux): restyle dashboard — hero preview, status pill, empty state, list cap"
```

---

## Slice C — Events + Settings (Tasks 6–7)

### Task 6: Restyle the Events page (filter bar + states)

**Files:** Modify `src/curbcam/web/templates/events.html`, `src/curbcam/web/templates/partials/events_rows.html`.

- [ ] **Step 1: Update `events.html`**

Preserve `form.filters` (hx-get → `#rows`), `a.csv`, `#rows.event-list` + `data-units`. Lay the filter controls in a styled, wrapping bar:

```html
{% extends "base.html" %}
{% block title %} · Events{% endblock %}
{% block content %}
<h1>Events</h1>
<form class="filters card" hx-get="/api/events" hx-target="#rows" hx-swap="innerHTML"
      style="display:flex;flex-wrap:wrap;gap:var(--sp-3);align-items:end;padding:var(--sp-4)">
  <label>From<br><input type="date" name="start"></label>
  <label>To<br><input type="date" name="end"></label>
  <label>Min speed<br><input type="number" step="0.1" name="min_speed"></label>
  <label>Max speed<br><input type="number" step="0.1" name="max_speed"></label>
  <label>Direction<br>
    <select name="direction">
      <option value="">Any</option>
      <option value="L2R">&gt;&gt;</option>
      <option value="R2L">&lt;&lt;</option>
    </select>
  </label>
  <button type="submit" class="btn-primary">Filter</button>
  <a class="csv btn" href="/api/events.csv" style="margin-left:auto">Export CSV</a>
</form>
<section id="rows" class="event-list" data-units="{{ units }}">
  {% include "partials/events_rows.html" %}
</section>
{% endblock %}
```

- [ ] **Step 2: Add an empty state to `events_rows.html`**

Preserve the `event_card` include and `.load-more` button; add a zero-results state:

```html
{% for e in events %}
  {% include "partials/event_card.html" %}
{% else %}
  <p class="empty">No events match these filters.</p>
{% endfor %}
{% if next_cursor %}
<button class="load-more btn"
        hx-get="/api/events?{{ query }}&cursor={{ next_cursor }}"
        hx-target="this" hx-swap="outerHTML">Load more</button>
{% endif %}
```

- [ ] **Step 3: Verify**

On `/events`: filter bar is a styled card that wraps on narrow widths; Filter still swaps `#rows` (htmx works); Export CSV link still tracks the filters (change a filter, confirm `a.csv` href updates — `app.js` syncs it); "Load more" paginates; a no-match filter shows the empty state. Light + dark.

- [ ] **Step 4: Commit**
```bash
git add src/curbcam/web/templates/events.html src/curbcam/web/templates/partials/events_rows.html
git commit -m "feat(ux): restyle Events — filter bar, empty state, load-more"
```

---

### Task 7: Restyle Settings

**Files:** Modify `src/curbcam/web/templates/settings.html`, `src/curbcam/web/templates/partials/settings_form.html`.

- [ ] **Step 1: Add settings-specific layout to `app.css`**

Append:
```css
fieldset{border:1px solid var(--border);border-radius:var(--radius);background:var(--surface-1);
  padding:var(--sp-4) var(--sp-5);margin:0 0 var(--sp-4)}
legend{font-weight:600;color:var(--text-muted);padding:0 var(--sp-2)}
.setting{display:grid;grid-template-columns:200px 1fr;gap:var(--sp-2) var(--sp-4);align-items:center;margin-bottom:var(--sp-3)}
.setting small.help{grid-column:2} .setting .badge-env{grid-column:2;justify-self:start}
.setting .field-error{grid-column:2}
.saved-ok{color:var(--ok);margin-left:var(--sp-3)}
section.danger{border:1px solid var(--danger);border-radius:var(--radius);padding:var(--sp-4) var(--sp-5);margin-top:var(--sp-6)}
section.danger h2{color:var(--danger);margin-top:0}
@media (max-width:560px){.setting{grid-template-columns:1fr}.setting small.help,.setting .badge-env,.setting .field-error{grid-column:1}}
```

- [ ] **Step 2: Mark the danger Delete button**

In `settings.html`, give the purge submit a danger class (keep the `hx-post`/`hx-confirm`):
```html
<section class="danger">
  <h2>Delete old events</h2>
  <form hx-post="/api/events/purge" hx-confirm="Delete events older than the given days?">
    <input type="number" name="days" value="30" min="1">
    <button type="submit" class="btn-danger">Delete</button>
  </form>
</section>
```
(`settings_form.html` keeps its structure — `#settings-form`, `.setting`, `.badge-env`, `.field-error`, `.saved-ok` are already there and now styled by Step 1. No markup change needed beyond what's styled.)

- [ ] **Step 3: Verify**

On `/settings`: Primary/Advanced fieldsets are styled cards with aligned label/control/help rows; the "set via environment" badge renders on env-set fields; Save & restart still posts and swaps `#settings-form` (htmx); the Delete action is red and still shows the confirm. Mint-token form still appends to `#token-list`. Narrow width collapses rows to one column. Light + dark.

- [ ] **Step 4: Commit**
```bash
git add src/curbcam/web/static/app.css src/curbcam/web/templates/settings.html
git commit -m "feat(ux): restyle Settings — fieldset cards, env badge, danger styling"
```

---

## Slice D — Wizard + calibration/alignment (Tasks 8–10)

### Task 8: Wizard stepper + password/configure screens + preview onerror fix

**Files:** Modify `src/curbcam/web/templates/setup/password.html`, `src/curbcam/web/templates/setup/configure.html`, `src/curbcam/web/static/app.css`. **Leave `setup/index.html` unchanged** — it is only a dispatcher (`{% if need_password %} include password.html {% else %} include configure.html {% endif %}`); it owns no form/markup to restyle.

- [ ] **Step 1: Add stepper + setup styles to `app.css`**

```css
.stepper{display:flex;gap:var(--sp-2);list-style:none;padding:0;margin:0 0 var(--sp-5);flex-wrap:wrap}
.stepper li{display:flex;align-items:center;gap:var(--sp-2);color:var(--text-muted);font-size:var(--fs-1)}
.stepper li::before{content:attr(data-n);display:grid;place-items:center;width:1.6rem;height:1.6rem;
  border-radius:50%;background:var(--surface-3);color:var(--text-muted);font-size:var(--fs-0)}
.stepper li.done::before{background:var(--accent);color:var(--on-accent);content:"✓"}
.stepper li.current{color:var(--text);font-weight:600}
.stepper li.current::before{background:var(--accent);color:var(--on-accent)}
.setup-card{max-width:520px;margin:var(--sp-6) auto}
.preview-frame{position:relative;max-width:640px;background:var(--surface-3);border-radius:var(--radius);
  aspect-ratio:4/3;display:grid;place-items:center;overflow:hidden}
.preview-frame img{width:100%;display:block}
.preview-frame .ph{position:absolute;color:var(--text-muted);font-size:var(--fs-1)}
```

- [ ] **Step 2: Restyle `setup/password.html` — stepper + card INSIDE the form**

`password.html` IS the form, and it's the htmx swap unit (`#setup-step`, replaced outerHTML by `configure.html` on submit). So the stepper + welcome card must go **inside** the `<form id="setup-step">` (anything outside it would survive the swap and leave a stale stepper above the configure view). Keep the form attrs + input verbatim:

```html
<form id="setup-step" class="setup-card card" hx-post="/api/setup/password" hx-target="#setup-step" hx-swap="outerHTML">
  <ol class="stepper">
    <li class="current" data-n="1">Password</li><li data-n="2">Privacy</li>
    <li data-n="3">Camera</li><li data-n="4">Align</li><li data-n="5">Calibrate</li>
  </ol>
  <h1>Welcome to curbcam</h1>
  <p class="help">Set an admin password to begin — it's the only account, used to reach the dashboard and settings.</p>
  <input type="password" name="password" placeholder="Choose a password" required minlength="6">
  <button type="submit" class="btn-primary">Set password</button>
</form>
```
(`setup/index.html` is untouched — it just includes this partial when `need_password`.)

- [ ] **Step 3: Update `setup/configure.html` (steps 2–5) + preview onerror/retry**

Preserve `#ack`, the camera `<form hx-post="/api/setup/camera" hx-target="#camera-result">`, `#camera-result`, `#setup-preview`, and the align/calibrate links. Add the stepper, a framed preview with a placeholder, and an **`onerror` retry** so a not-yet-ready stream (camera restart race, spec §6.2) shows a placeholder instead of a broken image:

```html
<div id="setup-step">
  <ol class="stepper">
    <li class="done" data-n="1">Password</li><li class="current" data-n="2">Privacy</li>
    <li data-n="3">Camera</li><li data-n="4">Align</li><li data-n="5">Calibrate</li>
  </ol>
  <h2>2 · Before you start</h2>
  <p>Speed cameras capture people and vehicles in public spaces. <strong>Check your
  local laws</strong> before pointing this at a road. Nothing leaves this device.</p>
  <label><input type="checkbox" id="ack"> I understand</label>

  <h2>3 · Camera source</h2>
  <form hx-post="/api/setup/camera" hx-target="#camera-result" hx-swap="innerHTML">
    <input name="source" placeholder="picamera2:0 | usb:0 | rtsp://... | file:./fixtures" required>
    <button type="submit" class="btn-primary">Use this camera</button>
  </form>
  <span id="camera-result" class="help"></span>

  <h2>4 · Confirm preview</h2>
  <div class="preview-frame">
    <span class="ph">Starting camera…</span>
    <img id="setup-preview" src="/api/stream.mjpeg" alt="live preview"
         onerror="this.dataset.tries=(+this.dataset.tries||0)+1; if(this.dataset.tries<20){this.src='';setTimeout(()=>{this.src='/api/stream.mjpeg?_='+Date.now();},1500);}">
  </div>

  <h2>5 · Align &amp; calibrate</h2>
  <a href="/setup/align" class="btn">Set detection region »</a>
  <a href="/setup/calibrate" class="btn btn-primary">Calibrate speed »</a>
</div>
```

- [ ] **Step 4: Verify**

Fresh first-run (clear `_ux/data` + restart, or a new data dir): `/setup` shows the stepper + centered welcome card; set the password; steps 2–5 show the stepper (step 1 ✓, step 2 current); the preview shows "Starting camera…" then the live feed (no broken-image icon) — and if you save a new camera source (triggering a restart) it recovers via retry rather than breaking. Light + dark.

- [ ] **Step 5: Commit**
```bash
git add src/curbcam/web/templates/setup/password.html src/curbcam/web/templates/setup/configure.html src/curbcam/web/static/app.css
git commit -m "feat(ux): wizard stepper + setup cards + self-healing live-preview (onerror retry)"
```

---

### Task 9: Theme-aware canvas colors (calibrate.js + align.js)

**Files:** Modify `src/curbcam/web/static/calibrate.js`, `src/curbcam/web/static/align.js`.

- [ ] **Step 1: Read the accent/marker color from CSS in `calibrate.js`**

In `src/curbcam/web/static/calibrate.js`, replace the hardcoded `"red"` fills/strokes with a value read from a CSS variable. Add a helper near the top of the IIFE and use it in `redraw()`:

```javascript
  const cssVar = (name, fallback) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
```
Then in `redraw()` replace the two lines:
```javascript
    ctx.fillStyle = "red";
    ctx.strokeStyle = "red";
```
with:
```javascript
    const mark = cssVar("--accent", "#0a7d5a");
    ctx.fillStyle = mark;
    ctx.strokeStyle = mark;
```

- [ ] **Step 2: Same for `align.js`**

In `src/curbcam/web/static/align.js`, add the same `cssVar` helper near the top of the IIFE, and in `redraw()` replace:
```javascript
    ctx.strokeStyle = "lime";
```
with:
```javascript
    ctx.strokeStyle = cssVar("--accent", "#0a7d5a");
```

- [ ] **Step 3: Verify** (together with Task 10)

Deferred to Task 10's verification (the calibration/alignment screens must be styled first to see the canvas in context).

- [ ] **Step 4: Commit**
```bash
git add src/curbcam/web/static/calibrate.js src/curbcam/web/static/align.js
git commit -m "feat(ux): canvas marker colors read --accent (theme-aware), no hardcoded red/lime"
```

---

### Task 10: Restyle calibration + alignment screens

**Files:** Modify `src/curbcam/web/templates/setup/calibrate.html`, `src/curbcam/web/templates/setup/align.html`.

- [ ] **Step 1: Restyle `setup/calibrate.html`**

Preserve EVERY id (`#capture #frame #cal-canvas #pixel-distance #undo #reset #distance #units #direction #submit #result`) and keep `#frame`+`#cal-canvas` inside a `.canvas-wrap` so the canvas overlays the image (spec §5.4). Lay controls vertically; group the measurement controls. Example (adapt to the current file's exact ids):

```html
{% extends "base.html" %}
{% block title %} · Calibrate{% endblock %}
{% block content %}
<h1>Calibrate speed</h1>
<ol class="stepper"><li class="done" data-n="1">Password</li><li class="done" data-n="2">Privacy</li>
  <li class="done" data-n="3">Camera</li><li class="done" data-n="4">Align</li><li class="current" data-n="5">Calibrate</li></ol>
<ol class="help">
  <li>Place a known-length object in view (fence panel, parked car, chalk line).</li>
  <li>Capture, then click its two ends on the frozen frame.</li>
  <li>Enter the real-world distance and which direction this lane carries.</li>
</ol>
<button id="capture" class="btn-primary">Capture reference frame</button>
<div class="canvas-wrap card" style="padding:0;margin-top:var(--sp-4)">
  <img id="frame" alt="reference frame">
  <canvas id="cal-canvas"></canvas>
</div>
<div class="cal-controls" style="display:flex;flex-wrap:wrap;gap:var(--sp-3);align-items:end;margin-top:var(--sp-4)">
  <span><span id="pixel-distance">0 px</span> measured</span>  <!-- keep #pixel-distance a span (calibrate.js sets .textContent) -->
  <button id="undo">Undo point</button>
  <button id="reset">Start over</button>
  <label>Distance<br><input id="distance" type="number" step="0.01"></label>
  <label>Units<br><select id="units"><option>m</option><option>ft</option><option>in</option><option>mm</option></select></label>
  <label>Direction<br><select id="direction"><option value="L2R">&gt;&gt;</option><option value="R2L">&lt;&lt;</option></select></label>
  <button id="submit" class="btn-primary">Save calibration</button>
</div>
<p id="result" class="help"></p>
<script src="/static/calibrate.js" defer></script>
{% endblock %}
```
IMPORTANT: confirm the current `calibrate.html` `<script>` include and any existing ids/option values; copy the exact `#units`/`#direction` option values from the current file (don't invent values the backend rejects). Only restructure layout + classes.

- [ ] **Step 2: Restyle `setup/align.html`**

Preserve `#align-frame #align-canvas #overlay-toggle #save-crop #align-result`, keep `#align-frame`+`#align-canvas` in a `.canvas-wrap`. Add the stepper + a styled save button + the overlay toggle as a labeled control. (Mirror the calibrate structure; keep the current file's script include and ids.)

- [ ] **Step 3: Verify — the high-risk active checks (spec §9)**

Run the e2e calibration smoke (it captures a frame and **clicks the canvas** — proves the overlay/z-index didn't regress):
```bash
uv run --no-sync pytest tests/e2e/test_calibrate_smoke.py -q -m e2e
```
Expected: PASS. Then manually (file-replay app): on `/setup/calibrate`, Capture shows the frozen frame in the framed card; clicking two points draws **accent-colored** dots/line (not red) and updates "N px"; toggle dark theme and re-capture — the markers are still visible/contrasting; Save works. On `/setup/align`, drag draws an **accent** rectangle and Save posts. Confirm clicks register (canvas on top).

- [ ] **Step 4: Commit**
```bash
git add src/curbcam/web/templates/setup/calibrate.html src/curbcam/web/templates/setup/align.html
git commit -m "feat(ux): restyle calibration + alignment (canvas overlay preserved, theme-aware markers)"
```

---

## Slice E — A11y, responsive, finalize (Task 11)

### Task 11: Accessibility, responsive pass, full visual sweep, finalize

**Files:** Modify `src/curbcam/web/static/app.css` (responsive/a11y tweaks), `src/curbcam/web/static/app.js` (aria-live).

- [ ] **Step 1: aria-live on the live regions**

In `app.js`, when wiring SSE, mark the event list + pill as polite live regions so screen readers announce updates. After `const list = document.getElementById("event-list");` guard, add:
```javascript
  if (list) list.setAttribute("aria-live", "polite");
  const pillEl = document.getElementById("tracking-pill");
  if (pillEl) pillEl.setAttribute("aria-live", "polite");
```

- [ ] **Step 2: Responsive + reduced-motion in `app.css`**

Append:
```css
@media (max-width:600px){
  .main{padding:var(--sp-4) var(--sp-3)}
  .nav{gap:var(--sp-2)} .nav a:not(.brand){padding:var(--sp-1)}
  .event-list{grid-template-columns:1fr 1fr}
}
@media (max-width:400px){.event-list{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
```

- [ ] **Step 3: Full visual + interaction sweep (Playwright), both themes**

With the file-replay app + a seeded calibration, screenshot each screen in light and dark at desktop and 390px: `/`, `/events`, `/settings`, `/setup`, `/setup/calibrate`, `/setup/align`. Confirm: AA-ish contrast in both themes; visible focus ring when tabbing; nav/grid/filter-bar reflow on mobile; no theme flash on reload. Fix any contrast/spacing issues by adjusting tokens (not structure).

- [ ] **Step 4: Full regression gate**
```bash
uv run --no-sync ruff check . && uv run --no-sync ruff format --check . && uv run --no-sync mypy src/curbcam
uv run --no-sync pytest -q                      # unit/integration unaffected
uv run --no-sync pytest tests/e2e/test_calibrate_smoke.py -q -m e2e   # canvas-click flow
```
Expected: all green. (No Python changed, so unit/integration are unaffected; the e2e smoke proves calibration still works through the restyle.)

- [ ] **Step 5: Confirm no §5.4 hook was lost**
```bash
# Every preserved id/class should still appear in templates/js:
grep -rEo "id=\"(frame|cal-canvas|pixel-distance|result|capture|undo|reset|submit|distance|units|direction|align-frame|align-canvas|align-result|overlay-toggle|save-crop|event-list|tracking-pill|preview|rows|settings-form|token-list|camera-result|setup-preview)\"" src/curbcam/web/templates | sort -u
grep -rE "class=\"filters|class=\"csv|event-card|event-meta|\"speed\"|\"dir\"|load-more" src/curbcam/web/templates | head
```
Eyeball that the calibration/align/dashboard/events/settings hooks are all still present.

- [ ] **Step 6: Clean up + commit**
```bash
rm -rf _ux
git add src/curbcam/web/static/app.css src/curbcam/web/static/app.js
git commit -m "feat(ux): a11y (aria-live, focus, contrast) + responsive pass + final sweep"
```

---

## Notes for the implementer

- **Read spec §5.4 first.** The single biggest failure mode is renaming/removing a JS-queried id/class or breaking the canvas overlay z-index — it fails silently (no error, just dead clicks / unstyled live cards). The grep in Task 11 Step 5 and the e2e smoke are your safety nets; run the smoke after Slice D.
- **Two card paths (Tasks 3+4) ship together** — never restyle `event_card.html` without updating the `app.js` builder in the same slice, or SSE-inserted cards break.
- **Colors are a starting palette,** not gospel — the `--accent` and surface tokens are real working values; tune them, but keep AA contrast in both themes.
- **No Python changes** anywhere; if you feel the urge to touch a route, you've left scope (the only allowed behavior touch is the client-side preview `onerror`, Task 8).
- Keep the existing `*.js` IIFE/structure; only the specified blocks change.

## Self-Review

**Spec coverage:** §5.1 design system → Task 1–2 (tokens, theme, components; single-file app.css is a deliberate simplification of the spec's two-file suggestion, noted in the file map). §5.4 hooks → Ground rules + Task 11 grep + e2e. §6.1 shell/nav/favicon → Task 1. §6.2 wizard stepper + preview fix → Task 8 (onerror retry, correct race-condition fix). §6.3 calibration/alignment → Tasks 9–10. §6.4 dashboard cap/empty/pill → Tasks 4–5. §6.5 events → Task 6. §6.6 settings → Task 7. §7 cross-cutting (favicon T1, preview T8, cap/empty T5, a11y/responsive T11). §9 verification (active canvas via e2e smoke T10; SSE card parity T4; both themes throughout; gates T11). No gaps.

**Placeholder scan:** none — every step gives real CSS/markup/JS or exact commands. The two "adapt to the current file's exact ids/option values" notes (Tasks 8, 10) are deliberate safety instructions to copy load-bearing values verbatim, not missing content.

**Consistency:** token names (`--accent`, `--surface-*`, `--fs-speed`, etc.) are defined in Task 1 and reused unchanged in Tasks 2/7/8; the event-card classes (`.event-card/.event-meta/.speed/.dir`) are identical across the partial (Task 3), the `app.js` builder (Task 4), and the CSS (Task 2); `data-cap` set in Task 5 is read in Task 4.

This plan is on branch `design/ux-uplift` (the spec is already committed there).
