let categoryChart = null;

async function loadStats() {
  const response = await apiFetch("/dashboard/stats");
  if (!response) return;
  if (!response.ok) return;

  const stats = await response.json();

  document.querySelectorAll("[data-stat]").forEach((el) => {
    const key = el.getAttribute("data-stat");
    el.textContent = stats[key] ?? "0";
  });

  renderCategoryChart(stats.category_breakdown || {});
}

function renderCategoryChart(breakdown) {
  const canvas = document.getElementById("categoryChart");
  if (!canvas) return;

  const labels = Object.keys(breakdown);
  const values = Object.values(breakdown);

  if (categoryChart) {
    categoryChart.destroy();
    categoryChart = null;
  }
  const empty = labels.length === 0;
  canvas.classList.toggle("d-none", empty);
  document.getElementById("categoryEmpty").classList.toggle("d-none", !empty);
  if (empty || typeof Chart === "undefined") return;

  categoryChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: [
          "#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#dc3545",
          "#fd7e14", "#ffc107", "#198754", "#20c997", "#6c757d",
        ],
      }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: "76%",
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, padding: 20 } } },
    },
  });
}

function wireSyncButton() {
  const btn = document.getElementById("syncBtn");
  if (!btn) return;

  const spinner = document.getElementById("syncSpinner");
  const resultBox = document.getElementById("syncResult");
  const olderBtn = document.getElementById("olderSyncBtn");
  let nextPageToken = null;

  async function syncBatch(older) {
    btn.disabled = true;
    olderBtn.disabled = true;
    spinner.classList.remove("d-none");
    btn.setAttribute("aria-busy", "true");
    resultBox.classList.add("d-none");
    document.getElementById("lastSync").textContent = "Syncing your messages… this may take a moment.";

    try {
      let url = "/gmail/sync?max_results=25";
      if (older && nextPageToken) url += `&page_token=${encodeURIComponent(nextPageToken)}`;
      const response = await apiFetch(url, { method: "POST" });
      if (!response) return;

      const data = await response.json().catch(() => ({
        error: `Sync failed (HTTP ${response.status}). Check the Flask terminal for details.`,
      }));
      resultBox.classList.remove("d-none", "alert-info", "alert-danger");

      if (response.ok) {
        nextPageToken = data.next_page_token || null;
        resultBox.classList.add("alert-info");
        resultBox.textContent = `Synced ${data.synced} new email(s), checked ${data.skipped_existing} already-known. ${nextPageToken ? "More older emails are available." : "No more older emails in this batch sequence."}`;
        loadStats();
        document.getElementById("lastSync").textContent = `Last synced ${new Date().toLocaleTimeString()}`;
      } else {
        resultBox.classList.add("alert-danger");
        resultBox.textContent = data.error || "Sync failed.";
        document.getElementById("lastSync").textContent = "Sync did not complete. You can try again.";
      }
    } catch (err) {
      resultBox.classList.remove("d-none", "alert-info");
      resultBox.classList.add("alert-danger");
      resultBox.textContent = "Could not complete sync. Check that Flask is running and see its terminal for details.";
      document.getElementById("lastSync").textContent = "Sync did not complete.";
    } finally {
      btn.disabled = false;
      olderBtn.disabled = !nextPageToken;
      spinner.classList.add("d-none");
      btn.removeAttribute("aria-busy");
    }
  }
  btn.addEventListener("click", () => syncBatch(false));
  olderBtn.addEventListener("click", () => syncBatch(true));
}

document.addEventListener("DOMContentLoaded", () => {
  loadStats();
  wireSyncButton();
});
