// Alignment wizard: drag a crop rect over the live MJPEG, scale display->source,
// POST it. Safe DOM only.
(() => {
  const frame = document.getElementById("align-frame");
  const canvas = document.getElementById("align-canvas");
  const ctx = canvas.getContext("2d");
  const result = document.getElementById("align-result");
  let start = null;
  let rect = null; // SOURCE coords [x0,y0,x1,y1]
  const cssVar = (name, fallback) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

  function scale() { return frame.naturalWidth / frame.clientWidth; }

  function sizeCanvas() {
    canvas.width = frame.clientWidth;
    canvas.height = frame.clientHeight;
  }
  frame.addEventListener("load", sizeCanvas);
  window.addEventListener("resize", sizeCanvas);

  function toDisp(v) { return v / scale(); }

  function redraw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!rect) return;
    ctx.strokeStyle = cssVar("--accent", "#0a7d5a");
    ctx.lineWidth = 2;
    ctx.strokeRect(toDisp(rect[0]), toDisp(rect[1]),
                   toDisp(rect[2] - rect[0]), toDisp(rect[3] - rect[1]));
  }

  canvas.addEventListener("mousedown", (e) => {
    const r = canvas.getBoundingClientRect();
    start = [e.clientX - r.left, e.clientY - r.top];
  });
  canvas.addEventListener("mousemove", (e) => {
    if (!start) return;
    const r = canvas.getBoundingClientRect();
    const s = scale();
    const cur = [e.clientX - r.left, e.clientY - r.top];
    rect = [
      Math.round(Math.min(start[0], cur[0]) * s),
      Math.round(Math.min(start[1], cur[1]) * s),
      Math.round(Math.max(start[0], cur[0]) * s),
      Math.round(Math.max(start[1], cur[1]) * s),
    ];
    redraw();
  });
  window.addEventListener("mouseup", () => { start = null; });

  document.getElementById("overlay-toggle").addEventListener("change", (e) => {
    frame.src = e.target.checked ? "/api/stream.mjpeg?overlay=1" : "/api/stream.mjpeg";
  });

  document.getElementById("save-crop").addEventListener("click", async () => {
    if (!rect) { result.textContent = "Drag a rectangle first."; return; }
    const resp = await fetch("/api/crop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x0: rect[0], y0: rect[1], x1: rect[2], y1: rect[3] }),
    });
    result.textContent = resp.ok ? "Saved — detector restarting." : "Invalid region.";
  });
})();
