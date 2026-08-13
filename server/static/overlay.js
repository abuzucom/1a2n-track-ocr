// Split out of overlay.html so the Caddyfile's default-src 'self'
// Content-Security-Policy does not block it. An inline <script> needs
// either 'unsafe-inline' or a per-deploy hash; an external file needs
// neither.

const POLL_INTERVAL_MS = 5000;

async function refresh() {
  try {
    const response = await fetch("/output/now_playing.json", { cache: "no-store" });
    const data = await response.json();
    const players = Object.values(data.players || {});
    const first = players[0];
    // textContent, never innerHTML: the track string is OCR output and
    // is not trusted markup.
    document.getElementById("track").textContent = first ? first.track : "";
    document.getElementById("artist").textContent = first && first.artist ? first.artist : "";
  } catch (error) {
    console.error("now_playing.json fetch failed, keeping last known value:", error);
  }
}

refresh();
setInterval(refresh, POLL_INTERVAL_MS);
