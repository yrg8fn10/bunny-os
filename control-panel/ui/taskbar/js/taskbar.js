// Bunny taskbar behavior: Mac-style magnification on hover, running dots,
// launches through the local loopback server, a soft clock. No framework,
// no telemetry, no network beyond 127.0.0.1.
const APPS = [
  { id: "bunny", name: "Bun Bun" },
  { id: "steam", name: "Steam" },
  { id: "files", name: "Files" },
  { id: "browser", name: "Browser" },
  { id: "terminal", name: "Terminal" },
  { id: "settings", name: "Settings" },
];
const buttons = APPS.map((a) => document.getElementById("app-" + a.id));
const tip = document.getElementById("tip");
const dock = document.getElementById("dock");

// Magnification: the hovered glyph swells, neighbours lean along.
function setMagnification(center) {
  const index = center === null ? null : buttons.indexOf(center);
  buttons.forEach((b, i) => {
    let mag = 1;
    if (index !== null) {
      const d = Math.abs(i - index);
      mag = d === 0 ? 1.38 : d === 1 ? 1.18 : d === 2 ? 1.05 : 1;
    }
    b.querySelector(".glyph").style.setProperty("--mag", mag);
  });
}

buttons.forEach((b) => {
  b.addEventListener("mouseenter", () => {
    setMagnification(b);
    const app = APPS.find((a) => "app-" + a.id === b.id);
    tip.textContent = app ? app.name : "";
    tip.classList.add("on");
  });
  b.addEventListener("mouseleave", () => {
    setMagnification(null);
    tip.classList.remove("on");
  });
  b.addEventListener("click", async () => {
    b.querySelector(".glyph").animate(
      [{ transform: "translateY(0)" }, { transform: "translateY(-7px)" }, { transform: "translateY(0)" }],
      { duration: 260, easing: "cubic-bezier(0.34,1.6,0.64,1)" }
    );
    try { await fetch("/api/launch", { method: "POST", body: JSON.stringify({ id: b.dataset.app }) }); }
    catch (e) { /* the server went away; the dock stays up and retries on the next state poll */ }
  });
});
dock.addEventListener("mouseleave", () => tip.classList.remove("on"));

// Running dots refresh from the loopback server.
async function refreshRunning() {
  try {
    const res = await fetch("/api/state");
    const state = await res.json();
    for (const app of state.apps || []) {
      const dot = document.querySelector('[data-dot="' + app.id + '"]');
      if (dot) dot.classList.toggle("on", !!app.running);
    }
  } catch (e) { /* offline tick; next one will land */ }
}
refreshRunning();
setInterval(refreshRunning, 3000);

// The clock, Mac-menu-bar style.
function tick() {
  const now = new Date();
  document.getElementById("clock-day").textContent =
    now.toLocaleDateString(undefined, { weekday: "short" });
  document.getElementById("clock-time").textContent =
    now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
tick();
setInterval(tick, 1000);
