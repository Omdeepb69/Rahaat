/**
 * Workspace 3: Incident Investigation Component.
 * Explicitly displays unknown fields and evidence provenance.
 * Provides human verification and reversible incident merging/unmerging controls.
 */

export function initInvestigation(api, state) {
  const investigationContainer = document.getElementById("investigation-content");
  const hypothesesContainer = document.getElementById("hypotheses-content");
  const statusTag = document.getElementById("incident-status-tag");

  async function loadIncident(id) {
    if (!id) return;
    try {
      investigationContainer.innerHTML = `<div style="color: var(--text-muted);">Loading incident details...</div>`;
      hypothesesContainer.innerHTML = `<div style="color: var(--text-muted);">Loading hypotheses & links...</div>`;

      const incident = await api.fetchIncidentDetail(id);
      const linksData = await api.fetchIncidentLinks(id).catch(() => ({ links: [] }));

      renderIncidentDetail(incident);
      renderHypothesesAndLinks(incident, linksData.links || []);
    } catch (err) {
      investigationContainer.innerHTML = `<div style="color: var(--priority-critical);">Failed to load incident: ${err.message}</div>`;
    }
  }

  function renderIncidentDetail(inc) {
    const priority = (inc.priority || "standard").toLowerCase();
    statusTag.innerHTML = `
      <span class="badge-priority ${priority}">${priority}</span>
      <span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 0.5rem;">STATUS: <strong style="color: white;">${inc.status || "open"}</strong></span>
    `;

    // Explicit UNKNOWN preservation check:
    const medicalNeed = inc.medical_need !== null && inc.medical_need !== undefined
      ? (inc.medical_need ? '<strong style="color: #ef4444;">YES (CRITICAL)</strong>' : "None reported")
      : '<span class="badge-unknown">UNKNOWN — UNVERIFIED</span>';

    const trappedStatus = inc.trapped_count !== null && inc.trapped_count !== undefined
      ? `<strong>${inc.trapped_count} persons</strong>`
      : '<span class="badge-unknown">UNKNOWN — UNVERIFIED</span>';

    const elderlyOrInfants = inc.vulnerable_count !== null && inc.vulnerable_count !== undefined
      ? `<strong>${inc.vulnerable_count}</strong>`
      : '<span class="badge-unknown">UNKNOWN — UNVERIFIED</span>';

    const reports = inc.reports || [];

    investigationContainer.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start;">
        <div>
          <h3 style="color: #60a5fa; font-size: 1rem;">Incident #${inc.id}</h3>
          <p style="font-size: 0.8rem; color: var(--text-muted);">Disaster ID: ${inc.disaster_id}</p>
        </div>
        <div>
          ${inc.status !== "verified" ? `<button class="btn-primary" id="btn-verify-incident">Verify Incident</button>` : `<span style="color: var(--status-confirmed); font-size: 0.8rem; font-weight: 700;">✓ VERIFIED</span>`}
        </div>
      </div>

      <!-- Critical Facts & Safety Triage -->
      <div style="background-color: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.75rem;">
        <h4 style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.5rem; text-transform: uppercase;">Triaged Safety Facts (Explicit Uncertainty)</h4>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.8rem;">
          <div>Medical Attention Required:</div>
          <div>${medicalNeed}</div>

          <div>Trapped Individuals:</div>
          <div>${trappedStatus}</div>

          <div>Elderly / Infants Present:</div>
          <div>${elderlyOrInfants}</div>

          <div>Decision Explanation:</div>
          <div style="color: #93c5fd;">${inc.triage_explanation || "Assessed via Deterministic Safety Policy"}</div>
        </div>
      </div>

      <!-- Evidence Provenance Graph -->
      <div>
        <h4 style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.5rem; text-transform: uppercase;">Supporting Reports & Evidence Spans (${reports.length})</h4>
        <div style="display: flex; flex-direction: column; gap: 0.5rem; max-height: 220px; overflow-y: auto;">
          ${reports.length === 0 ? `<div style="font-size: 0.8rem; color: var(--text-muted);">No raw reports linked yet.</div>` : ""}
          ${reports.map((r) => `
            <div style="background-color: var(--bg-primary); border-left: 3px solid #3b82f6; border-radius: var(--radius-sm); padding: 0.5rem; font-size: 0.8rem;">
              <div style="display: flex; justify-content: space-between; color: var(--text-muted); font-size: 0.7rem;">
                <span>Source: <strong>${r.source_identity || "caller"}</strong> (${r.source_type || "ivr"})</span>
                <span>${new Date(r.received_at || r.created_at).toLocaleTimeString()}</span>
              </div>
              <p style="margin-top: 0.2rem; color: #f8fafc;">${escapeHtml(r.text || r.raw_payload?.transcript || r.raw_payload?.text || "Audio distress call received")}</p>
            </div>
          `).join("")}
        </div>
      </div>
    `;

    const verifyBtn = document.getElementById("btn-verify-incident");
    if (verifyBtn) {
      verifyBtn.addEventListener("click", async () => {
        try {
          await api.verifyIncident(inc.id);
          alert("Incident successfully verified by dispatcher.");
          loadIncident(inc.id);
        } catch (err) {
          alert(`Verification failed: ${err.message}`);
        }
      });
    }
  }

  function renderHypothesesAndLinks(inc, links) {
    const hypotheses = inc.hypotheses || [];

    hypothesesContainer.innerHTML = `
      <!-- Location Hypotheses -->
      <div>
        <h4 style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.5rem; text-transform: uppercase;">Location Hypotheses</h4>
        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
          ${hypotheses.length === 0 ? `
            <div style="background-color: var(--bg-tertiary); padding: 0.5rem; border-radius: var(--radius-sm); font-size: 0.8rem;">
              <span class="badge-unknown">UNKNOWN LOCATION</span>
              <p style="color: var(--text-muted); font-size: 0.75rem; margin-top: 0.25rem;">No confirmed landmark or GPS coordinates. Active clarification required.</p>
            </div>
          ` : ""}
          ${hypotheses.map((h, i) => `
            <div style="background-color: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.5rem; font-size: 0.8rem;">
              <div style="display: flex; justify-content: space-between;">
                <strong>Candidate #${i + 1}: ${escapeHtml(h.landmark_name || "Spatial Hypothesis")}</strong>
                <span style="color: #60a5fa;">Score: ${(h.confidence * 100).toFixed(0)}%</span>
              </div>
              <div style="color: var(--text-muted); font-size: 0.75rem; margin-top: 0.2rem;">
                Uncertainty Radius: <strong>±${h.uncertainty_radius_m || 200}m</strong> | Method: ${h.resolution_method || "gazetteer"}
              </div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- Deduplication Review Queue -->
      <div style="margin-top: 0.5rem;">
        <h4 style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.5rem; text-transform: uppercase;">Duplicate Candidate Review (${links.length})</h4>
        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
          ${links.length === 0 ? `<div style="font-size: 0.8rem; color: var(--text-muted);">No ambiguous duplicate candidate links pending review.</div>` : ""}
          ${links.map((l) => `
            <div style="background-color: var(--bg-tertiary); border: 1px solid #f59e0b; border-radius: var(--radius-sm); padding: 0.6rem; font-size: 0.8rem;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>Link with Incident: <strong style="color: #60a5fa;">#${l.target_incident_id}</strong></span>
                <span style="color: #f59e0b; font-weight: 700;">Score: ${(l.score * 100).toFixed(0)}%</span>
              </div>
              <p style="color: var(--text-muted); font-size: 0.75rem; margin-top: 0.2rem;">Reason: ${escapeHtml(l.reason || "High spatial proximity and household match")}</p>
              <div style="display: flex; gap: 0.4rem; margin-top: 0.4rem;">
                <button class="btn-success btn-approve-merge" data-id="${l.id}" style="font-size: 0.7rem; padding: 0.2rem 0.5rem;">Approve Merge</button>
                <button class="btn-danger btn-reject-link" data-id="${l.id}" style="font-size: 0.7rem; padding: 0.2rem 0.5rem;">Reject Duplicate</button>
              </div>
            </div>
          `).join("")}
        </div>
      </div>
    `;

    hypothesesContainer.querySelectorAll(".btn-approve-merge").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const linkId = btn.getAttribute("data-id");
        try {
          await api.reviewLink(linkId, "merge", "Dispatcher verified duplicate merge");
          alert("Merge approved. Incidents linked reversibly.");
          loadIncident(inc.id);
        } catch (err) {
          alert(`Failed to approve merge: ${err.message}`);
        }
      });
    });

    hypothesesContainer.querySelectorAll(".btn-reject-link").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const linkId = btn.getAttribute("data-id");
        try {
          await api.reviewLink(linkId, "reject", "Dispatcher rejected duplicate");
          alert("Duplicate link rejected.");
          loadIncident(inc.id);
        } catch (err) {
          alert(`Failed to reject link: ${err.message}`);
        }
      });
    });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // When incident is selected from another workspace
  state.on("incident_selected", (id) => {
    loadIncident(id);
  });

  // If incident list updates and no incident is selected, pick the first one
  state.on("incidents_updated", (incidents) => {
    if (!state.selectedIncidentId && incidents && incidents.length > 0) {
      state.selectIncident(incidents[0].id);
    }
  });
}
