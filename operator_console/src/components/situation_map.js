/**
 * Workspace 2: Situation Map Component.
 * Enforces Critical UI Safety Rule:
 * Distinct visual encodings for confirmed, candidate, approximate, stale, and contradictory locations.
 */

export function initSituationMap(api, state) {
  const container = document.getElementById("map-markers-layer");

  function renderMapMarkers() {
    if (!container) return;
    container.innerHTML = "";

    const incidents = state.incidents || [];
    const resources = state.resources || [];

    // Fallback coordinate mapping for synthetic or district coordinates
    // Center around Kerala / district bounds: Lat: 9.93, Lon: 76.26
    const baseLat = 9.9312;
    const baseLon = 76.2673;

    // Render Incident Markers
    incidents.forEach((inc, idx) => {
      // Determine status: confirmed, candidate, approximate, stale, contradictory
      const locStatus = inc.location_status || (inc.location ? "confirmed" : "candidate");
      const priority = (inc.priority || "standard").toLowerCase();

      // Pseudo-spatial positioning for interactive visualization
      const xPercent = 25 + ((idx * 17 + 10) % 55);
      const yPercent = 20 + ((idx * 23 + 15) % 60);

      // Uncertainty radius representation (meters mapped to pixels)
      const radiusMeters = inc.uncertainty_radius_m || 250;
      const radiusPx = Math.min(Math.max(radiusMeters / 5, 24), 90);

      // 1. Uncertainty Bounding Ring (for candidate and approximate locations)
      if (locStatus === "candidate" || locStatus === "approximate" || locStatus === "contradictory") {
        const circle = document.createElement("div");
        circle.className = `uncertainty-circle ${locStatus}`;
        circle.style.left = `${xPercent}%`;
        circle.style.top = `${yPercent}%`;
        circle.style.width = `${radiusPx * 2}px`;
        circle.style.height = `${radiusPx * 2}px`;
        circle.title = `Uncertainty radius: ±${radiusMeters}m (${locStatus})`;
        container.appendChild(circle);
      }

      // 2. Main Location Marker Pin
      const marker = document.createElement("div");
      marker.className = "map-marker";
      marker.style.left = `${xPercent}%`;
      marker.style.top = `${yPercent}%`;

      const glyph = document.createElement("div");
      glyph.className = `marker-glyph pin-${locStatus}`;

      // Glyphs: Confirmed -> checkmark, Candidate -> ?, Stale -> clock, Contradictory -> !
      if (locStatus === "confirmed") {
        glyph.innerHTML = "✓";
        glyph.title = `CONFIRMED RESCUE PIN: Incident ${inc.id}`;
      } else if (locStatus === "candidate") {
        glyph.innerHTML = "?";
        glyph.title = `UNVERIFIED CANDIDATE LOCATION (±${radiusMeters}m): Requires human review`;
      } else if (locStatus === "approximate") {
        glyph.innerHTML = "~";
        glyph.title = `APPROXIMATE AREA ESTIMATE: Incident ${inc.id}`;
      } else if (locStatus === "stale") {
        glyph.innerHTML = "◷";
        glyph.title = `STALE COORDINATES (>2h old): Incident ${inc.id}`;
      } else if (locStatus === "contradictory") {
        glyph.innerHTML = "!";
        glyph.title = `CONTRADICTORY LOCATION ALERT: Discrepancy detected between sources`;
      }

      marker.appendChild(glyph);

      // Popup on Click
      const popup = document.createElement("div");
      popup.className = "map-popup";
      popup.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: #60a5fa;">Incident #${String(inc.id).slice(0, 8)}</strong>
          <span class="badge-priority ${priority}">${priority}</span>
        </div>
        <div style="font-size: 0.75rem; color: #94a3b8;">
          Location Status: <strong class="text-${locStatus}" style="text-transform: uppercase;">${locStatus}</strong>
        </div>
        <div style="font-size: 0.75rem;">
          Uncertainty: <strong>±${radiusMeters}m</strong>
        </div>
        <div style="margin-top: 0.4rem; display: flex; gap: 0.4rem;">
          <button class="btn-primary btn-inspect-map" style="font-size: 0.7rem; padding: 0.2rem 0.4rem;">Investigate</button>
          <button class="btn-success btn-dispatch-map" style="font-size: 0.7rem; padding: 0.2rem 0.4rem;">Dispatch</button>
        </div>
      `;

      marker.appendChild(popup);

      marker.addEventListener("click", (e) => {
        e.stopPropagation();
        document.querySelectorAll(".map-popup").forEach((p) => p.classList.remove("visible"));
        popup.classList.toggle("visible");
      });

      popup.querySelector(".btn-inspect-map").addEventListener("click", (e) => {
        e.stopPropagation();
        state.selectIncident(inc.id);
        state.setWorkspace("investigation");
      });

      popup.querySelector(".btn-dispatch-map").addEventListener("click", (e) => {
        e.stopPropagation();
        state.selectIncident(inc.id);
        state.setWorkspace("operations");
      });

      container.appendChild(marker);
    });

    // Render Resource Markers
    resources.forEach((res, idx) => {
      const xPercent = 15 + ((idx * 21 + 5) % 75);
      const yPercent = 15 + ((idx * 31 + 8) % 70);

      const marker = document.createElement("div");
      marker.className = "map-marker";
      marker.style.left = `${xPercent}%`;
      marker.style.top = `${yPercent}%`;

      const badge = document.createElement("div");
      badge.className = `marker-resource ${res.resource_type || "boat"}`;
      badge.innerHTML = `<span>🚤</span> <span>${escapeHtml(res.name)}</span>`;
      badge.title = `Resource: ${res.name} (${res.availability_status || "available"})`;

      marker.appendChild(badge);
      container.appendChild(marker);
    });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // Refresh on workspace switch or data updates
  state.on("workspace_changed", (ws) => {
    if (ws === "map") {
      renderMapMarkers();
    }
  });

  state.on("incidents_updated", renderMapMarkers);
  state.on("resources_updated", renderMapMarkers);

  // Close popups when clicking map background
  document.getElementById("situation-map").addEventListener("click", () => {
    document.querySelectorAll(".map-popup").forEach((p) => p.classList.remove("visible"));
  });
}
