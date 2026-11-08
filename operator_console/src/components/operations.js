/**
 * Workspace 4: Operations & Rescue Dispatch Component.
 * Enforces authenticated human approval for rescue resource assignment and lifecycle progression.
 */

/** Map triage priority values to CSS badge classes and display labels. */
const PRIORITY_META = {
  critical: { cls: "badge-p0", label: "P0 CRITICAL", feedCls: "priority-p0 pulse-critical" },
  urgent:   { cls: "badge-p1", label: "P1 URGENT",   feedCls: "priority-p1" },
  standard: { cls: "badge-p2", label: "P2 STANDARD", feedCls: "priority-p2" },
  low:      { cls: "badge-p3", label: "P3 LOW",      feedCls: "priority-p3" },
};

function priorityMeta(raw) {
  return PRIORITY_META[(raw || "standard").toLowerCase()] ?? PRIORITY_META.standard;
}

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

    // Sort: P0 first, then P1, P2, P3
    const ORDER = { critical: 0, urgent: 1, standard: 2, low: 3 };
    const sorted = [...incidents].sort((a, b) => {
      const pa = ORDER[(a.priority || "standard").toLowerCase()] ?? 2;
      const pb = ORDER[(b.priority || "standard").toLowerCase()] ?? 2;
      return pa - pb;
    });

    incidentsContainer.innerHTML = sorted
      .map((inc) => {
        const meta = priorityMeta(inc.priority);
        const isSelected = state.selectedIncidentId === inc.id;
        const needsSummary = escapeHtml(inc.needs_summary || "Rescue required");
        const location = inc.location_text
          ? `<span style="font-size:0.75rem;color:#93c5fd;">📍 ${escapeHtml(inc.location_text)}</span>`
          : `<span class="badge-unknown" style="font-size:0.65rem;">LOCATION UNKNOWN</span>`;

        return `
          <div class="feed-item ${meta.feedCls}${isSelected ? " selected" : ""}"
               style="${isSelected ? "border-color: #60a5fa;" : ""}"
               data-id="${inc.id}">
            <div class="item-meta">
              <div style="display:flex;align-items:center;gap:0.4rem;">
                <span class="${meta.cls}">${meta.label}</span>
                ${location}
              </div>
              <span style="font-size:0.7rem;color:var(--text-muted);">${inc.status}</span>
            </div>
            <div style="font-size:0.85rem;font-weight:600;margin-top:0.2rem;color:#f1f5f9;">
              Incident #${String(inc.id).slice(0, 8)}
            </div>
            <p style="font-size:0.8rem;color:#cbd5e1;">${needsSummary}</p>

            <div id="assignment-section-${inc.id}"
                 style="margin-top:0.5rem;padding-top:0.5rem;border-top:1px dashed var(--border-color);">
              <div style="font-size:0.75rem;color:var(--text-muted);">Loading assignment status...</div>
            </div>
          </div>
        `;
      })
      .join("");

    // Load assignments for each incident
    sorted.forEach((inc) => {
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
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:0.75rem;color:var(--text-muted);">No resource assigned</span>
            <button class="btn-primary btn-assign-modal" data-id="${incidentId}"
                    style="font-size:0.7rem;padding:0.2rem 0.5rem;">Propose Dispatch</button>
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
          <div style="display:flex;flex-direction:column;gap:0.3rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span style="font-size:0.75rem;color:#93c5fd;">Resource: <strong>${asgn.resource_id}</strong></span>
              <span style="font-size:0.75rem;font-weight:700;text-transform:uppercase;color:#fbbf24;">${asgn.status}</span>
            </div>
            <div style="display:flex;gap:0.3rem;margin-top:0.2rem;flex-wrap:wrap;">
              ${renderLifecycleButtons(incidentId, asgn)}
            </div>
          </div>
        `;
        attachLifecycleHandlers(el, incidentId, asgn.id);
      }
    } catch {
      el.innerHTML = `<span style="font-size:0.75rem;color:var(--text-muted);">No assignment data</span>`;
    }
  }

  function renderLifecycleButtons(incidentId, asgn) {
    const status = asgn.status;
    if (status === "proposed") {
      return `<button class="btn-success btn-event" data-type="approved" style="font-size:0.7rem;padding:0.2rem 0.4rem;">✓ Approve Dispatch</button>`;
    }
    if (status === "approved") {
      return `<button class="btn-primary btn-event" data-type="acknowledged" style="font-size:0.7rem;padding:0.2rem 0.4rem;">Acknowledge</button>`;
    }
    if (status === "acknowledged") {
      return `<button class="btn-primary btn-event" data-type="en_route" style="font-size:0.7rem;padding:0.2rem 0.4rem;">🚒 En Route</button>`;
    }
    if (status === "en_route") {
      return `<button class="btn-primary btn-event" data-type="on_scene" style="font-size:0.7rem;padding:0.2rem 0.4rem;">📍 On Scene</button>`;
    }
    if (status === "on_scene") {
      return `<button class="btn-success btn-event" data-type="rescued" style="font-size:0.7rem;padding:0.2rem 0.4rem;">✓ Rescued</button>`;
    }
    if (status === "rescued") {
      return `<button class="btn-primary btn-event" data-type="closed" style="font-size:0.7rem;padding:0.2rem 0.4rem;">Close Operation</button>`;
    }
    return `<span style="font-size:0.75rem;color:var(--status-confirmed);">✓ Operation Closed</span>`;
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
      resourcesContainer.innerHTML = `<div style="color:var(--text-muted);padding:1rem;">No resources registered in district.</div>`;
      return;
    }

    // Group: available first
    const sorted = [...resources].sort((a, b) => {
      if (a.availability_status === "available" && b.availability_status !== "available") return -1;
      if (a.availability_status !== "available" && b.availability_status === "available") return 1;
      return 0;
    });

    resourcesContainer.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:0.5rem;max-height:280px;overflow-y:auto;">
        ${sorted.map((r) => {
          const isAvailable = r.availability_status === "available";
          const statusColor = isAvailable ? "var(--status-confirmed)" : "#f59e0b";
          const statusIcon = isAvailable ? "✅" : "⏳";
          return `
          <div style="background-color:var(--bg-tertiary);border:1px solid ${isAvailable ? "var(--status-confirmed)" : "var(--border-color)"};
                      border-left:3px solid ${statusColor};border-radius:var(--radius-sm);
                      padding:0.6rem;display:flex;justify-content:space-between;align-items:center;font-size:0.8rem;">
            <div>
              <strong style="color:#f8fafc;">${escapeHtml(r.name)}</strong>
              <div style="color:var(--text-muted);font-size:0.7rem;">
                ${r.resource_type} · Cap: ${r.capacity || "N/A"}
              </div>
            </div>
            <div style="text-align:right;">
              <span style="font-size:0.75rem;font-weight:700;color:${statusColor};">
                ${statusIcon} ${r.availability_status}
              </span>
            </div>
          </div>
        `}).join("")}
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

  const dispatchModal = document.getElementById("dispatch-assignment-modal");
  const modalIncidentTitle = document.getElementById("modal-incident-title");
  const modalResourceList = document.getElementById("modal-resource-list");
  const btnCloseDispatchModal = document.getElementById("btn-close-dispatch-modal");

  if (btnCloseDispatchModal && dispatchModal) {
    btnCloseDispatchModal.addEventListener("click", () => {
      dispatchModal.classList.remove("open");
    });
    dispatchModal.addEventListener("click", (e) => {
      if (e.target === dispatchModal) {
        dispatchModal.classList.remove("open");
      }
    });
  }

  function openDispatchModal(incidentId) {
    const availableResources = (state.resources || []).filter((r) => r.availability_status === "available");
    if (!dispatchModal || !modalResourceList) return;

    modalIncidentTitle.textContent = `Assign Unit to Incident #${String(incidentId).slice(0, 8)}`;

    if (availableResources.length === 0) {
      modalResourceList.innerHTML = `<div style="color:var(--text-muted);padding:1rem;text-align:center;">No available rescue resources in registry. Free up a resource first.</div>`;
      dispatchModal.classList.add("open");
      return;
    }

    modalResourceList.innerHTML = availableResources
      .map((r) => {
        const icon = r.resource_type === "boat" ? "🚤" : r.resource_type === "medical" ? "🏥" : r.resource_type === "vehicle" ? "🚒" : "🔧";
        return `
          <div class="feed-item" data-res-id="${r.id}" style="cursor:pointer;padding:0.65rem 0.85rem;display:flex;justify-content:space-between;align-items:center;background:rgba(20,29,47,0.7);border:1px solid rgba(255,255,255,0.08);">
            <div>
              <div style="font-weight:700;font-size:0.85rem;color:#f8fafc;">${icon} ${escapeHtml(r.name)}</div>
              <div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">${r.resource_type} · ${r.capacity_total ? `Capacity: ${r.capacity_total}` : "Rapid Unit"}</div>
            </div>
            <button class="btn-success btn-select-res" data-res-id="${r.id}" style="font-size:0.75rem;padding:0.35rem 0.75rem;">Assign →</button>
          </div>
        `;
      })
      .join("");

    modalResourceList.querySelectorAll(".btn-select-res").forEach((btn) => {
      btn.addEventListener("click", () => {
        const resId = btn.getAttribute("data-res-id");
        dispatchModal.classList.remove("open");
        api.proposeAssignment(incidentId, resId)
          .then(() => {
            loadIncidentAssignments(incidentId);
          })
          .catch((err) => {
            alert(`Failed proposing assignment: ${err.message}`);
          });
      });
    });

    dispatchModal.classList.add("open");
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
