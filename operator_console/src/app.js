/**
 * Main application bootstrap for Raahat 2.0 Operator Console.
 */

import { RaahatAPI } from "./api.js";
import { ConsoleState } from "./state.js";
import { initReportsFeed } from "./components/reports_feed.js";
import { initSituationMap } from "./components/situation_map.js";
import { initInvestigation } from "./components/investigation.js";
import { initOperations } from "./components/operations.js";

document.addEventListener("DOMContentLoaded", () => {
  const api = new RaahatAPI();
  const state = new ConsoleState();

  // ── 1. Dispatcher Identity ──────────────────────────────────────────────
  const dispatcherDisplay = document.getElementById("dispatcher-id-display");
  const dispatcherBadge = document.getElementById("dispatcher-badge");
  const dispatcherModal = document.getElementById("dispatcher-modal");
  const inputDispatcherId = document.getElementById("input-dispatcher-id");
  const btnSaveDispatcher = document.getElementById("btn-save-dispatcher");

  if (dispatcherDisplay) {
    dispatcherDisplay.textContent = api.dispatcherId.slice(0, 8) + "...";
    inputDispatcherId.value = api.dispatcherId;
  }

  dispatcherBadge.addEventListener("click", () => dispatcherModal.classList.add("open"));

  btnSaveDispatcher.addEventListener("click", () => {
    const val = inputDispatcherId.value.trim();
    if (val) {
      api.setDispatcherId(val);
      dispatcherDisplay.textContent = val.slice(0, 8) + "...";
    }
    dispatcherModal.classList.remove("open");
  });

  dispatcherModal.addEventListener("click", (e) => {
    if (e.target === dispatcherModal) dispatcherModal.classList.remove("open");
  });

  // ── 2. Tab Navigation ───────────────────────────────────────────────────
  const tabButtons = document.querySelectorAll(".tab-btn");
  const panels = document.querySelectorAll(".workspace-panel");

  function switchWorkspace(target) {
    tabButtons.forEach((btn) => {
      const isTarget = btn.getAttribute("data-workspace") === target;
      btn.classList.toggle("active", isTarget);
      btn.setAttribute("aria-selected", isTarget ? "true" : "false");
    });
    panels.forEach((panel) => {
      panel.classList.toggle("active", panel.id === `workspace-${target}`);
    });
    state.setWorkspace(target);
  }

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => switchWorkspace(btn.getAttribute("data-workspace")));
  });

  // ── 3. Disaster Switcher ────────────────────────────────────────────────
  const disasterSelect = document.getElementById("disaster-select");

  async function loadDisasterList() {
    try {
      const disasters = await api.fetchDisasters({ limit: 50 }).catch(() => []);
      if (!disasters || disasters.length === 0) {
        disasterSelect.innerHTML = `<option value="">No registered disasters</option>`;
        return;
      }

      disasterSelect.innerHTML = disasters
        .map((d) => `<option value="${d.id}">${d.name} [${d.status.toUpperCase()}]</option>`)
        .join("");

      const active = await api.fetchActiveDisaster().catch(() => disasters[0]);
      if (active && active.id) {
        disasterSelect.value = active.id;
        state.setActiveDisaster(active.id);
      } else {
        state.setActiveDisaster(disasters[0].id);
      }
    } catch {
      disasterSelect.innerHTML = `<option value="">Unavailable</option>`;
    }
  }

  disasterSelect.addEventListener("change", () => {
    const id = disasterSelect.value;
    if (id) state.setActiveDisaster(id);
  });

  // ── 4. Live IST Clock ───────────────────────────────────────────────────
  const clockEl = document.getElementById("telemetry-clock");
  if (clockEl) {
    const fmtOpts = { timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" };
    const tick = () => { clockEl.textContent = `${new Date().toLocaleTimeString("en-GB", fmtOpts)} IST`; };
    tick();
    setInterval(tick, 1000);
  }

  // ── 5. KPI Banner — Live Data ───────────────────────────────────────────
  const kpiP0 = document.getElementById("kpi-p0");
  const kpiTrapped = document.getElementById("kpi-trapped");
  const kpiReports = document.getElementById("kpi-reports");
  const kpiResources = document.getElementById("kpi-resources");

  async function refreshKPIs() {
    try {
      const disasterId = state.activeDisasterId;
      if (!disasterId) return;

      const [incidents, resources, reports] = await Promise.allSettled([
        api.fetchIncidents({ disaster_id: disasterId, limit: 200 }),
        api.fetchResources({ disaster_id: disasterId }),
        api.fetchReports({ disaster_id: disasterId, limit: 200 }),
      ]);

      if (incidents.status === "fulfilled") {
        const list = Array.isArray(incidents.value) ? incidents.value
          : (incidents.value.items || []);

        const p0 = list.filter((i) =>
          ["critical_review", "critical"].includes(i.operational_priority)
        ).length;
        if (kpiP0) kpiP0.textContent = p0;

        const trapped = list.reduce((sum, i) => {
          return sum + (i.severity_facts?.people_count || 0);
        }, 0);
        if (kpiTrapped) kpiTrapped.textContent = trapped || "—";
      }

      if (resources.status === "fulfilled") {
        const avail = (resources.value || []).filter((r) => r.availability_status === "available").length;
        if (kpiResources) kpiResources.textContent = avail;
      }

      if (reports.status === "fulfilled") {
        const list = Array.isArray(reports.value) ? reports.value
          : (reports.value.items || []);
        if (kpiReports) kpiReports.textContent = list.length;
      }
    } catch (err) {
      console.warn("KPI refresh error:", err);
    }
  }

  // Refresh KPIs whenever the disaster changes or incidents update
  state.on("disaster_changed", () => refreshKPIs());
  state.on("incidents_updated", () => refreshKPIs());
  state.on("report_added", () => {
    if (kpiReports) kpiReports.textContent = parseInt(kpiReports.textContent || 0) + 1;
  });

  // ── 6. Initialize Workspace Components ─────────────────────────────────
  initReportsFeed(api, state);
  initSituationMap(api, state);
  initInvestigation(api, state);
  initOperations(api, state);

  // Load disaster list (triggers state.setActiveDisaster → disaster_changed → refreshKPIs)
  loadDisasterList();

  // ── 7. Live SSE Event Stream ────────────────────────────────────────────
  const streamIndicator = document.getElementById("stream-indicator");
  const streamText = document.getElementById("stream-text");

  try {
    api.connectEventStream(
      (event) => {
        if (streamIndicator) streamIndicator.classList.remove("disconnected");
        if (streamText) streamText.textContent = "LIVE SSE";
        streamText.style.color = "var(--status-confirmed)";

        if (event.event_type === "report.created") {
          state.addReport(event.payload);
        } else if (event.event_type?.startsWith("incident.")) {
          api.fetchIncidents({ limit: 20 }).then((res) => {
            state.setIncidents(res.items || res || []);
          });
        }
      },
      () => {
        if (streamIndicator) streamIndicator.classList.add("disconnected");
        if (streamText) {
          streamText.textContent = "POLLING";
          streamText.style.color = "var(--text-muted)";
        }
      }
    );
  } catch (err) {
    console.warn("SSE connection error:", err);
  }
});
