// Shared helpers: fetch JSON with friendly error banners when a service is down.
async function api(url, opts) {
  let r;
  try {
    r = await fetch(url, opts);
  } catch (e) {
    showAlert(`Dashboard backend unreachable (${e.message}).`);
    throw e;
  }
  const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok || data.error) {
    showAlert(data.error || `HTTP ${r.status}`);
    throw new Error(data.error || r.status);
  }
  return data;
}

function showAlert(msg, kind = "danger") {
  const box = document.getElementById("alerts");
  const div = document.createElement("div");
  div.className = `alert alert-${kind} alert-dismissible fade show`;
  div.innerHTML = `<strong>Service problem:</strong> ${escapeHtml(msg)}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
  box.appendChild(div);
}

function clearAlerts() { document.getElementById("alerts").innerHTML = ""; }

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmt(n, d = 0) {
  if (n === null || n === undefined || n === "") return "–";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
}

// validated categorical order (blue, orange, aqua, yellow, magenta, green, violet, red) - fixed, never cycled
// colour follows the entity: each Hive table keeps its colour in every chart
const TABLE_ORDER = ["obs_text", "obs_rc", "obs_rc_snappy", "obs_orc"];
const TABLE_COLOR = { obs_text: "#eb6834", obs_rc: "#2a78d6", obs_rc_snappy: "#1baf7a", obs_orc: "#eda100" };
const PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
if (window.Chart) { Chart.defaults.color = "#52514e"; Chart.defaults.borderColor = "#e6e6e3"; Chart.defaults.elements.bar.borderRadius = 4; Chart.defaults.elements.line.borderWidth = 2; Chart.defaults.elements.point.radius = 4; }
