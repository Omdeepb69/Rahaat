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

  // 3. Active Disaster Switcher (Fully Dynamic from /api/v1/disasters)
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

      // Attempt to set active disaster
      const active = await api.fetchActiveDisaster().catch(() => disasters[0]);
      if (active && active.id) {
        disasterSelect.value = active.id;
        state.setActiveDisaster(active.id);
      } else {
        state.setActiveDisaster(disasters[0].id);
      }
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

  // Live Operations Room Clock (IST)
  const clockEl = document.getElementById("telemetry-clock");
  if (clockEl) {
    function updateClock() {
      const now = new Date();
      const options = { timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" };
      clockEl.textContent = `${now.toLocaleTimeString("en-GB", options)} IST`;
    }
    updateClock();
    setInterval(updateClock, 1000);
  }

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
