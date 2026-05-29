// Render UTC timestamps in the browser's local zone.
function renderTimes(root) {
  root.querySelectorAll("time[datetime]").forEach((el) => {
    if (el.textContent) return;
    const d = new Date(el.getAttribute("datetime"));
    el.textContent = d.toLocaleString();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  renderTimes(document);

  const list = document.getElementById("event-list");
  if (list && list.dataset.sse) {
    const units = list.dataset.units || "kph";
    const es = new EventSource(list.dataset.sse);
    es.addEventListener("event", (m) => {
      const ev = JSON.parse(m.data);
      const speed = units === "mph"
        ? (ev.speed_kph / 1.609344).toFixed(1)
        : ev.speed_kph.toFixed(1);
      const arrow = ev.direction === "L2R" ? ">>" : "<<";

      // Build via DOM APIs (textContent / property assignment) rather than
      // innerHTML so event fields can never inject markup.
      const card = document.createElement("article");
      card.className = "event-card";

      const link = document.createElement("a");
      link.href = `/media/${ev.image_path}`;
      link.target = "_blank";
      const img = document.createElement("img");
      img.src = `/media/${ev.thumb_path}`;
      img.alt = `event ${ev.id}`;
      link.appendChild(img);

      const meta = document.createElement("div");
      meta.className = "event-meta";
      const speedEl = document.createElement("span");
      speedEl.className = "speed";
      speedEl.textContent = `${speed} ${units}`;
      const dirEl = document.createElement("span");
      dirEl.className = "dir";
      dirEl.textContent = arrow;
      const timeEl = document.createElement("time");
      timeEl.setAttribute("datetime", `${ev.ts_utc}Z`);
      meta.append(speedEl, dirEl, timeEl);

      card.append(link, meta);
      list.prepend(card);
      renderTimes(card);
    });
    es.addEventListener("stats", (m) => {
      const s = JSON.parse(m.data);
      const pill = document.getElementById("tracking-pill");
      if (!pill) return;
      pill.textContent = s.tracking ? "tracking" : `idle · ${s.fps ?? 0} fps`;
      pill.classList.toggle("active", !!s.tracking);
    });
  }
});
