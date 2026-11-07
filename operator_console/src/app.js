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

  // 1. Dispatcher Identity Management
  const dispatcherDisplay = document.getElementById("dispatcher-id-display");
  const dispatcherBadge = document.getElementById("dispatcher-badge");
  const dispatcherModal = document.getElementById("dispatcher-modal");
  const inputDispatcherId = document.getElementById("input-dispatcher-id");
  const btnSaveDispatcher = document.getElementById("btn-save-dispatcher");

  if (dispatcherDisplay) {
    dispatcherDisplay.textContent = api.dispatcherId;
    inputDispatcherId.value = api.dispatcherId;
  }

  dispatcherBadge.addEventListener("click", () => {
    dispatcherModal.classList.add("open");
  });

  btnSaveDispatcher.addEventListener("click", () => {
    const val = inputDispatcherId.value.trim();
    if (val) {
      api.setDispatcherId(val);
      dispatcherDisplay.textContent = val;
    }
    dispatcherModal.classList.remove("open");
  });

  dispatcherModal.addEventListener("click", (e) => {
    if (e.target === dispatcherModal) {
      dispatcherModal.classList.remove("open");
    }
  });

  // 2. Tab Navigation
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
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-workspace");
      switchWorkspace(target);
    });
  });

  state.on("workspace_changed", (ws) => {
    switchWorkspace(ws);
  });

  // 3. Active Disaster Switcher
  // No /api/v1/disasters endpoint exists; we derive the disaster list by
  // inspecting incident records (each carries a disaster_id) and deduplicate.
  const disasterSelect = document.getElementById("disaster-select");

  async function loadDisasterList() {
    try {
      const data = await api.fetchIncidents({ limit: 100 }).catch(() => ({ items: [] }));
      const incidents = data.items || data || [];

      // Collect unique disaster IDs from incidents
      const seen = new Set();
      const disasters = [];
      incidents.forEach((inc) => {
        if (inc.disaster_id && !seen.has(inc.disaster_id)) {
          seen.add(inc.disaster_id);
          disasters.push(inc.disaster_id);
        }
      });

      if (disasters.length === 0) {
        disasterSelect.innerHTML = `<option value="">No active disaster</option>`;
        return;
      }

      disasterSelect.innerHTML = disasters
        .map((id) => `<option value="${id}">${id.slice(0, 8)}…</option>`)
        .join("");

      // Default to first (most recent) disaster
      state.setActiveDisaster(disasters[0]);
    } catch {
      disasterSelect.innerHTML = `<option value="">Disaster list unavailable</option>`;
    }
  }

  disasterSelect.addEventListener("change", () => {
    const id = disasterSelect.value;
    if (id) {
      state.setActiveDisaster(id);
    }
  });

  // 4. Initialize Workspace Components
  initReportsFeed(api, state);
  initSituationMap(api, state);
  initInvestigation(api, state);
  initOperations(api, state);

  // Load disaster list after components are wired up so disaster_changed fires into them
  loadDisasterList();

  // 5. Live Event Stream (SSE) Integration
  const streamIndicator = document.getElementById("stream-indicator");
  const streamText = document.getElementById("stream-text");

  try {
    api.connectEventStream(
      (event) => {
        if (streamIndicator) streamIndicator.classList.remove("disconnected");
        if (streamText) streamText.textContent = "LIVE SSE";

        // Handle live incoming events
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
        if (streamText) streamText.textContent = "POLLING";
      }
    );
  } catch (err) {
    console.warn("SSE connection error:", err);
  }
});
