/**
 * Shared fetch helper for the pages in this app. If a session has expired
 * (or the user was never logged in), every JSON endpoint returns 401 —
 * this centralizes redirecting back to the login screen instead of every
 * page's script duplicating that check.
 */
async function apiFetch(url, options) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (response.status === 401) {
    window.location.href = "/";
    return null;
  }

  return response;
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

function formatTimestamp(isoString) {
  try {
    const normalized = typeof isoString === "string" && isoString.includes("T") && !/(Z|[+-]\d{2}:?\d{2})$/i.test(isoString) ? isoString + "Z" : isoString;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? (isoString || "") : date.toLocaleString();
  } catch (err) {
    return isoString;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("themeToggle");
  function updateThemeLabel() {
    const dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    if (toggle) {
      toggle.setAttribute("aria-pressed", String(dark));
      document.getElementById("themeLabel").textContent = dark ? "Light mode" : "Dark mode";
    }
  }
  updateThemeLabel();
  if (toggle) toggle.addEventListener("click", () => {
    const theme = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-bs-theme", theme);
    try { localStorage.setItem("emailorbit-theme", theme); } catch (_) {}
    const preview = document.getElementById("previewFrame");
    if (preview && preview.contentDocument) preview.contentDocument.documentElement.setAttribute("data-bs-theme", theme);
    updateThemeLabel();
  });
  document.querySelectorAll("time[datetime]").forEach(el => { el.textContent = formatTimestamp(el.dateTime); });
  if (toggle && !document.getElementById("statCards")) {
    apiFetch("/dashboard/stats").then(async response => {
      if (!response || !response.ok) return;
      const stats = await response.json();
      document.querySelectorAll(".sidebar-count[data-stat]").forEach(el => { el.textContent = stats[el.dataset.stat] || ""; });
    }).catch(() => {});
  }
});
