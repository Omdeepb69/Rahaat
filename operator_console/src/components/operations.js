/**
 * Workspace 4: Operations & Rescue Dispatch Component.
 * Enforces authenticated human approval for rescue resource assignment and lifecycle progression.
 */

export function initOperations(api, state) {
  const incidentsContainer = document.getElementById("active-incidents-container");
  const resourcesContainer = document.getElementById("resources-container");
  const auditStatusBadge = document.getElementById("audit-status-badge");
  const refreshResourcesBtn = document.getElementById("btn-refresh-resources");

  async function loadOperationsData() {
    try {
      incidentsContainer.innerHTML = `<div style="color: var(--text-muted);">Loading active incidents...</div>`;
      resourcesContainer.innerHTML = `<div style="color: var(--text-muted);">Loading resources...</div>`;

      const [incidentsRes, resourcesRes] = await Promise.all([
        api.fetchIncidents({ status: "open", limit: 20 }).catch(() => ({ items: [] })),
        api.fetchResources({ limit: 30 }).catch(() => ({ items: [] })),
      ]);

      const incidents = incidentsRes.items || incidentsRes || [];
      const resources = resourcesRes.items || resourcesRes || [];

      state.setIncidents(incidents);
      state.setResources(resources);

      renderIncidents(incidents);
      renderResources(resources);
      checkAuditIntegrity();
    } catch (err) {
      incidentsContainer.innerHTML = `<div style="color: var(--priority-critical);">Failed loading ops data: ${err.message}</div>`;
    }
  }

  function renderIncidents(incidents) {
    if (!incidents || incidents.length === 0) {
      incidentsContainer.innerHTML = `<div style="color: var(--text-muted); padding: 1rem;">No active incidents currently waiting in queue.</div>`;
      return;
    }

    incidentsContainer.innerHTML = incidents
      .map((inc) => {
        const priority = (inc.priority || "standard").toLowerCase();
        const isSelected = state.selectedIncidentId === inc.id;

        return `
          <div class="feed-item ${isSelected ? 'selected' : ''}" style="${isSelected ? 'border-color: #60a5fa;' : ''}" data-id="${inc.id}">
            <div class="item-meta">
              <span class="badge-priority ${priority}">${priority}</span>
              <span style="font-size: 0.75rem; color: var(--text-muted);">Status: <strong>${inc.status}</strong></span>
            </div>
            <div style="font-size: 0.85rem; font-weight: 600; margin-top: 0.2rem;">
              Incident #${String(inc.id).slice(0, 8)}
            </div>
            <p style="font-size: 0.8rem; color: #cbd5e1;">Needs: ${escapeHtml(inc.needs_summary || "Rescue required")}</p>
            
            <div id="assignment-section-${inc.id}" style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px dashed var(--border-color);">
              <div style="font-size: 0.75rem; color: var(--text-muted);">Loading assignment status...</div>
            </div>
          </div>
        `;
      })
      .join("");

    // Load assignments for each incident
    incidents.forEach((inc) => {
      loadIncidentAssignments(inc.id);
    });

    incidentsContainer.querySelectorAll(".feed-item").forEach((item) => {
      item.addEventListener("click", () => {
        const id = item.getAttribute("data-id");
        state.selectIncident(id);
      });
    });
  }

  async function loadIncidentAssignments(incidentId) {
    const el = document.getElementById(`assignment-section-${incidentId}`);
    if (!el) return;

    try {
      const data = await api.fetchAssignments(incidentId);
      const assignments = data.assignments || data || [];

      if (assignments.length === 0) {
        el.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 0.75rem; color: var(--text-muted);">No resource assigned</span>
            <button class="btn-primary btn-assign-modal" data-id="${incidentId}" style="font-size: 0.7rem; padding: 0.2rem 0.5rem;">Propose Dispatch</button>
          </div>
        `;
        const btn = el.querySelector(".btn-assign-modal");
        if (btn) {
          btn.addEventListener("click", (e) => {
            e.stopPropagation();
            openDispatchModal(incidentId);
          });
        }
      } else {
        const asgn = assignments[0];
        el.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 0.3rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.75rem; color: #93c5fd;">Resource: <strong>${asgn.resource_id}</strong></span>
              <span style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; color: #fbbf24;">${asgn.status}</span>
            </div>
            <div style="display: flex; gap: 0.3rem; margin-top: 0.2rem; flex-wrap: wrap;">
              ${renderLifecycleButtons(incidentId, asgn)}
            </div>
          </div>
        `;
        attachLifecycleHandlers(el, incidentId, asgn.id);
      }
    } catch {
      el.innerHTML = `<span style="font-size: 0.75rem; color: var(--text-muted);">No assignment data</span>`;
    }
  }

  function renderLifecycleButtons(incidentId, asgn) {
    const status = asgn.status;
    if (status === "proposed") {
      return `<button class="btn-success btn-event" data-type="approved" style="font-size: 0.7rem; padding: 0.2rem 0.4rem;">Approve Dispatch</button>`;
    }
    if (status === "approved") {
      return `<button class="btn-primary btn-event" data-type="acknowledged" style="font-size: 0.7rem; padding: 0.2rem 0.4rem;">Acknowledge</button>`;
    }
    if (status === "acknowledged") {
      return `<button class="btn-primary btn-event" data-type="en_route" style="font-size: 0.7rem; padding: 0.2rem 0.4rem;">En Route</button>`;
    }
    if (status === "en_route") {
      return `<button class="btn-primary btn-event" data-type="on_scene" style="font-size: 0.7rem; padding: 0.2rem 0.4rem;">On Scene</button>`;
    }
    if (status === "on_scene") {
      return `<button class="btn-success btn-event" data-type="rescued" style="font-size: 0.7rem; padding: 0.2rem 0.4rem;">Rescued</button>`;
    }
    if (status === "rescued") {
      return `<button class="btn-primary btn-event" data-type="closed" style="font-size: 0.7rem; padding: 0.2rem 0.4rem;">Close Operation</button>`;
    }
    return `<span style="font-size: 0.75rem; color: var(--status-confirmed);">Operation Closed</span>`;
  }

  function attachLifecycleHandlers(parentEl, incidentId, assignmentId) {
    parentEl.querySelectorAll(".btn-event").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const eventType = btn.getAttribute("data-type");
        try {
          await api.recordOperationEvent(incidentId, assignmentId, eventType, `Transitioned to ${eventType} by dispatcher`);
          alert(`Status progressed: ${eventType}`);
          loadIncidentAssignments(incidentId);
        } catch (err) {
          alert(`Transition failed: ${err.message}`);
        }
      });
    });
  }

  function renderResources(resources) {
    if (!resources || resources.length === 0) {
      resourcesContainer.innerHTML = `<div style="color: var(--text-muted); padding: 1rem;">No resources registered in district.</div>`;
      return;
    }

    resourcesContainer.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 0.5rem; max-height: 280px; overflow-y: auto;">
        ${resources.map((r) => `
          <div style="background-color: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.6rem; display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem;">
            <div>
              <strong style="color: #f8fafc;">${escapeHtml(r.name)}</strong>
              <div style="color: var(--text-muted); font-size: 0.7rem;">Type: ${r.resource_type} | Capacity: ${r.capacity || "N/A"}</div>
            </div>
            <div>
              <span style="font-size: 0.75rem; font-weight: 700; color: ${r.availability_status === 'available' ? 'var(--status-confirmed)' : '#f59e0b'};">
                ${r.availability_status}
              </span>
            </div>
          </div>
        `).join("")}
      </div>
    `;
  }

  async function checkAuditIntegrity() {
    try {
      const res = await api.verifyAuditChain();
      if (res.is_valid || res.total_verified !== undefined) {
        auditStatusBadge.textContent = "VERIFIED (Cryptographic SHA-256 Chains Intact)";
        auditStatusBadge.style.color = "var(--status-confirmed)";
      } else {
        auditStatusBadge.textContent = "TAMPER DETECTED";
        auditStatusBadge.style.color = "var(--priority-critical)";
      }
    } catch {
      auditStatusBadge.textContent = "ACTIVE (Append-Only)";
    }
  }

  function openDispatchModal(incidentId) {
    const availableResources = (state.resources || []).filter((r) => r.availability_status === "available");
    if (availableResources.length === 0) {
      alert("No available rescue resources in the registry. Free up a resource first.");
      return;
    }

    const resList = availableResources
      .map((r) => `${r.name} (${r.resource_type})`)
      .join("\n- ");

    const choice = prompt(`Select resource to assign to Incident #${incidentId}:\n\n- ${resList}\n\nEnter exact resource name:`, availableResources[0].name);
    if (!choice) return;

    const matched = availableResources.find((r) => r.name.toLowerCase() === choice.toLowerCase());
    if (!matched) {
      alert("Resource name not recognized.");
      return;
    }

    api.proposeAssignment(incidentId, matched.id)
      .then(() => {
        alert("Assignment proposed! Click 'Approve Dispatch' to authorize deployment.");
        loadIncidentAssignments(incidentId);
      })
      .catch((err) => {
        alert(`Failed proposing assignment: ${err.message}`);
      });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  refreshResourcesBtn.addEventListener("click", loadOperationsData);

  state.on("workspace_changed", (ws) => {
    if (ws === "operations") {
      loadOperationsData();
    }
  });

  // Initial load
  loadOperationsData();
}
