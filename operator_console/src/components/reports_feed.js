/**
 * Workspace 1: Incoming Reports Feed component.
 */

export function initReportsFeed(api, state) {
  const container = document.getElementById("reports-feed-container");
  const searchInput = document.getElementById("report-search");
  const channelFilter = document.getElementById("filter-channel");
  const statusFilter = document.getElementById("filter-status");
  const refreshBtn = document.getElementById("btn-refresh-reports");

  async function loadReports() {
    try {
      container.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 2rem;">Loading live reports...</div>`;
      const data = await api.fetchReports({
        channel: channelFilter.value || undefined,
        status: statusFilter.value || undefined,
        limit: 50,
      });
      const reports = data.items || data || [];
      state.setReports(reports);
      renderReports(reports);
    } catch (err) {
      container.innerHTML = `<div style="color: var(--priority-critical); padding: 1rem;">Failed to load reports: ${err.message}</div>`;
    }
  }

  function renderReports(reports) {
    if (!reports || reports.length === 0) {
      container.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 2rem;">No reports match the current filters.</div>`;
      return;
    }

    const query = searchInput.value.toLowerCase().trim();
    const filtered = reports.filter((r) => {
      if (!query) return true;
      const text = JSON.stringify(r.raw_payload || {}).toLowerCase();
      const phone = (r.source_identity || "").toLowerCase();
      return text.includes(query) || phone.includes(query);
    });

    container.innerHTML = filtered
      .map((r) => {
        const payload = r.raw_payload || {};
        const textPreview = payload.text || payload.transcript || payload.message || "No text transcript recorded";
        const channel = r.source_type || "web_sos";
        const time = new Date(r.received_at || r.created_at).toLocaleTimeString();

        return `
          <div class="feed-item" data-id="${r.id}" data-channel="${channel}">
            <div class="item-meta">
              <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span class="channel-tag ${channel}">${channel.replace("_", " ")}</span>
                <strong style="color: #cbd5e1;">${r.source_identity || "Unknown Source"}</strong>
              </div>
              <span>${time}</span>
            </div>
            <p style="font-size: 0.85rem; color: #f1f5f9; line-height: 1.4;">${escapeHtml(textPreview)}</p>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.3rem;">
              <span style="font-size: 0.75rem; color: var(--text-muted);">Status: <strong>${r.processing_status || "pending"}</strong></span>
              <button class="btn-primary btn-inspect-report" data-id="${r.id}" style="font-size: 0.75rem; padding: 0.2rem 0.5rem;">Inspect</button>
            </div>
          </div>
        `;
      })
      .join("");

    container.querySelectorAll(".btn-inspect-report").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const reportId = btn.getAttribute("data-id");
        state.selectedReportId = reportId;
        state.setWorkspace("investigation");
      });
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Event handlers
  refreshBtn.addEventListener("click", loadReports);
  channelFilter.addEventListener("change", loadReports);
  statusFilter.addEventListener("change", loadReports);
  searchInput.addEventListener("input", () => renderReports(state.reports));

  state.on("report_added", (newReport) => {
    renderReports(state.reports);
  });

  // Initial load
  loadReports();
}
