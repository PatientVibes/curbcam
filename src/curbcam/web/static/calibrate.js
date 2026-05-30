// Calibration wizard: capture a frozen frame, click two points (scaled from
// display coords back to SOURCE coords — the off-by-2x footgun in spec §8.7),
// submit a real-world distance. Uses safe DOM APIs (no innerHTML).
(() => {
  const frame = document.getElementById("frame");
  const canvas = document.getElementById("cal-canvas");
  const ctx = canvas.getContext("2d");
  const pixelOut = document.getElementById("pixel-distance");
  const result = document.getElementById("result");
  let points = []; // SOURCE-coordinate points
  const cssVar = (name, fallback) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

  function scale() {
    // naturalWidth is the SOURCE width of the captured JPEG.
    return frame.naturalWidth / frame.clientWidth;
  }

  function redraw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const s = scale();
    const mark = cssVar("--accent", "#0a7d5a");
    ctx.fillStyle = mark;
    ctx.strokeStyle = mark;
    ctx.lineWidth = 2;
    points.forEach((p) => {
      ctx.beginPath();
      ctx.arc(p[0] / s, p[1] / s, 5, 0, Math.PI * 2);
      ctx.fill();
    });
    if (points.length === 2) {
      ctx.beginPath();
      ctx.moveTo(points[0][0] / s, points[0][1] / s);
      ctx.lineTo(points[1][0] / s, points[1][1] / s);
      ctx.stroke();
      const dx = points[1][0] - points[0][0];
      const dy = points[1][1] - points[0][1];
      pixelOut.textContent = `${Math.round(Math.hypot(dx, dy))} px`;
    } else {
      pixelOut.textContent = "0 px";
    }
  }

  document.getElementById("capture").addEventListener("click", async () => {
    const resp = await fetch("/api/calibration/capture", { method: "POST" });
    if (!resp.ok) { result.textContent = "No frame yet — try again."; return; }
    const blob = await resp.blob();
    frame.src = URL.createObjectURL(blob);
    points = [];
  });

  frame.addEventListener("load", () => {
    canvas.width = frame.clientWidth;
    canvas.height = frame.clientHeight;
    redraw();
  });

  canvas.addEventListener("click", (e) => {
    if (points.length >= 2) return;
    const rect = canvas.getBoundingClientRect();
    const s = scale();
    points.push([(e.clientX - rect.left) * s, (e.clientY - rect.top) * s]);
    redraw();
  });

  document.getElementById("undo").addEventListener("click", () => { points.pop(); redraw(); });
  document.getElementById("reset").addEventListener("click", () => { points = []; redraw(); });

  document.getElementById("submit").addEventListener("click", async () => {
    if (points.length !== 2) { result.textContent = "Click two points first."; return; }
    const body = {
      points,
      distance: parseFloat(document.getElementById("distance").value),
      units: document.getElementById("units").value,
      direction: document.getElementById("direction").value,
    };
    const resp = await fetch("/api/calibration/measure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (resp.ok) {
      const data = await resp.json();
      result.textContent =
        `Saved: ${data.mm_per_px} mm/px (${data.direction}). ` +
        `Drive a known-speed vehicle past to verify, then go to the dashboard.`;
    } else {
      result.textContent = "Could not save — check your inputs.";
    }
  });
})();
