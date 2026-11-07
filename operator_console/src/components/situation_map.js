/**
 * Workspace 2: Situation Map Component.
 * Enforces Critical UI Safety Rule:
 * Distinct visual encodings for confirmed, candidate, approximate, stale, and contradictory locations.
 *
 * Renders an interactive Leaflet map when the library is available (loaded via CDN in HTML),
 * falling back to the SVG canvas overlay when it is not.
 */

/** Priority labels aligned to the operations component */
const PRIORITY_BADGE = {
  critical: "badge-p0",
  urgent:   "badge-p1",
  standard: "badge-p2",
  low:      "badge-p3",
};

/** Colour lookup for Leaflet circle markers by location status */
const LOC_STATUS_COLOR = {
  confirmed:    "#10b981",
  candidate:    "#f59e0b",
  approximate:  "#8b5cf6",
  stale:        "#6b7280",
  contradictory:"#dc2626",
};

/** Glyph & label for each location status */
const LOC_STATUS_GLYPH = {
  confirmed:    { g: "✓", label: "CONFIRMED" },
  candidate:    { g: "?", label: "CANDIDATE" },
  approximate:  { g: "~", label: "APPROXIMATE" },
  stale:        { g: "◷", label: "STALE" },
  contradictory:{ g: "!", label: "CONTRADICTORY" },
};

export function initSituationMap(api, state) {
  const container = document.getElementById("map-markers-layer");
  const mapEl = document.getElementById("situation-map");

  // Kerala district centre used for the interactive map default view
  const DEFAULT_LAT = 9.9312;
  const DEFAULT_LON = 76.2673;

  let leafletMap = null;
  let leafletLayerGroup = null;

  // Attempt to initialise Leaflet when available (loaded from CDN before this module runs)
  function tryInitLeaflet() {
    if (typeof window === "undefined" || !window.L || leafletMap) return false;
    try {
      // Leaflet requires the host element to have a concrete height
      mapEl.classList.remove("map-canvas-fallback");
      mapEl.style.height = "100%";

      leafletMap = window.L.map("situation-map").setView([DEFAULT_LAT, DEFAULT_LON], 11);
      window.L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        { attribution: "© OpenStreetMap contributors", maxZoom: 18 }
      ).addTo(leafletMap);

      leafletLayerGroup = window.L.layerGroup().addTo(leafletMap);
      return true;
    } catch {
      return false;
    }
  }

  // ── Leaflet render path ──────────────────────────────────────────────────────

  function renderLeafletMarkers() {
    if (!leafletLayerGroup) return;
    leafletLayerGroup.clearLayers();

    const incidents = state.incidents || [];
    const resources = state.resources || [];

    incidents.forEach((inc) => {
      const locStatus = inc.location_status || (inc.location ? "confirmed" : "candidate");
      const priority = (inc.priority || "standard").toLowerCase();
      const color = LOC_STATUS_COLOR[locStatus] ?? LOC_STATUS_COLOR.candidate;
      const radiusM = inc.uncertainty_radius_m || 250;
      const meta = LOC_STATUS_GLYPH[locStatus] ?? LOC_STATUS_GLYPH.candidate;
      const badgeCls = PRIORITY_BADGE[priority] ?? PRIORITY_BADGE.standard;

      // Fall back to seeded pseudo-coordinates when no real location is attached
      const lat = inc.location?.lat ?? (DEFAULT_LAT + ((parseInt(inc.id.slice(0, 4), 16) % 100) - 50) * 0.001);
      const lon = inc.location?.lon ?? (DEFAULT_LON + ((parseInt(inc.id.slice(4, 8), 16) % 100) - 50) * 0.001);

      // Uncertainty circle
      if (locStatus !== "confirmed") {
        window.L.circle([lat, lon], {
          radius: radiusM,
          color,
          fillColor: color,
          fillOpacity: 0.1,
          dashArray: locStatus === "candidate" ? "6 4" : undefined,
          weight: 1,
        }).addTo(leafletLayerGroup);
      }

      // Coloured circle marker
      const circleMarker = window.L.circleMarker([lat, lon], {
        radius: 10,
        color,
        fillColor: color,
        fillOpacity: 0.85,
        weight: 2,
      });

      circleMarker.bindPopup(`
        <div style="min-width:200px;font-family:sans-serif;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <strong style="color:#1d4ed8;">Incident #${String(inc.id).slice(0, 8)}</strong>
            <span style="font-size:0.65rem;padding:1px 5px;border-radius:9999px;
                         background:rgba(0,0,0,0.1);border:1px solid ${color};color:${color};">
              ${meta.label}
            </span>
          </div>
          <div style="font-size:0.8rem;color:#374151;">
            Priority: <strong>${priority}</strong> · ±${radiusM}m
          </div>
          ${inc.needs_summary ? `<div style="font-size:0.78rem;margin-top:4px;color:#374151;">${escapeHtml(inc.needs_summary)}</div>` : ""}
          <div style="display:flex;gap:6px;margin-top:8px;">
            <button onclick="window.__raahatInvestigate('${inc.id}')"
                    style="font-size:0.72rem;padding:2px 8px;background:#2563eb;color:white;border:none;border-radius:4px;cursor:pointer;">
              Investigate
            </button>
            <button onclick="window.__raahatDispatch('${inc.id}')"
                    style="font-size:0.72rem;padding:2px 8px;background:#059669;color:white;border:none;border-radius:4px;cursor:pointer;">
              Dispatch
            </button>
          </div>
        </div>
      `);

      circleMarker.addTo(leafletLayerGroup);
    });

    // Resource markers (boat / vehicle icons)
    resources.forEach((res) => {
      const icon = res.resource_type === "boat" ? "🚤"
        : res.resource_type === "medical" ? "🏥"
        : res.resource_type === "vehicle" ? "🚒" : "🔧";
      const lat = DEFAULT_LAT + (Math.random() - 0.5) * 0.05;
      const lon = DEFAULT_LON + (Math.random() - 0.5) * 0.05;

      window.L.marker([lat, lon], {
        icon: window.L.divIcon({
          html: `<div style="font-size:1.2rem;line-height:1;">${icon}</div>`,
          className: "",
          iconSize: [24, 24],
          iconAnchor: [12, 12],
        }),
      })
        .bindTooltip(`${res.name} — ${res.availability_status}`, { permanent: false })
        .addTo(leafletLayerGroup);
    });
  }

  // ── Fallback SVG/CSS render path (no Leaflet) ────────────────────────────────

  function renderFallbackMarkers() {
    if (!container) return;
    container.innerHTML = "";

    const incidents = state.incidents || [];
    const resources = state.resources || [];

    incidents.forEach((inc, idx) => {
      const locStatus = inc.location_status || (inc.location ? "confirmed" : "candidate");
      const priority = (inc.priority || "standard").toLowerCase();
      const radiusMeters = inc.uncertainty_radius_m || 250;
      const radiusPx = Math.min(Math.max(radiusMeters / 5, 24), 90);

      const xPercent = 25 + ((idx * 17 + 10) % 55);
      const yPercent = 20 + ((idx * 23 + 15) % 60);

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

      const marker = document.createElement("div");
      marker.className = "map-marker";
      marker.style.left = `${xPercent}%`;
      marker.style.top = `${yPercent}%`;

      const glyph = document.createElement("div");
      glyph.className = `marker-glyph pin-${locStatus}`;
      const meta = LOC_STATUS_GLYPH[locStatus] ?? LOC_STATUS_GLYPH.candidate;
      glyph.innerHTML = meta.g;
      glyph.title = `${meta.label}: Incident ${inc.id}`;
      marker.appendChild(glyph);

      const popup = document.createElement("div");
      popup.className = "map-popup";
      const badgeCls = PRIORITY_BADGE[priority] ?? PRIORITY_BADGE.standard;
      popup.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <strong style="color:#60a5fa;">Incident #${String(inc.id).slice(0, 8)}</strong>
          <span class="${badgeCls}">${priority}</span>
        </div>
        <div style="font-size:0.75rem;color:#94a3b8;">
          Location: <strong style="text-transform:uppercase;">${locStatus}</strong>
        </div>
        <div style="font-size:0.75rem;">Uncertainty: <strong>±${radiusMeters}m</strong></div>
        <div style="margin-top:0.4rem;display:flex;gap:0.4rem;">
          <button class="btn-primary btn-inspect-map" style="font-size:0.7rem;padding:0.2rem 0.4rem;">Investigate</button>
          <button class="btn-success btn-dispatch-map" style="font-size:0.7rem;padding:0.2rem 0.4rem;">Dispatch</button>
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

  // ── Unified render dispatcher ────────────────────────────────────────────────

  function renderMap() {
    if (leafletMap) {
      renderLeafletMarkers();
    } else {
      renderFallbackMarkers();
    }
  }

  // Expose action callbacks for Leaflet popup buttons (inline onclick can't close over module scope)
  window.__raahatInvestigate = (id) => {
    state.selectIncident(id);
    state.setWorkspace("investigation");
  };
  window.__raahatDispatch = (id) => {
    state.selectIncident(id);
    state.setWorkspace("operations");
  };

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // Refresh on workspace switch or data updates
  state.on("workspace_changed", (ws) => {
    if (ws === "map") {
      // Initialise Leaflet on first entry (the element is now visible so has dimensions)
      if (!leafletMap) tryInitLeaflet();
      // Leaflet needs a moment after display:flex kicks in
      setTimeout(() => {
        if (leafletMap) leafletMap.invalidateSize();
        renderMap();
      }, 50);
    }
  });

  state.on("incidents_updated", renderMap);
  state.on("resources_updated", renderMap);

  // Close fallback popups when clicking map background
  mapEl.addEventListener("click", () => {
    document.querySelectorAll(".map-popup").forEach((p) => p.classList.remove("visible"));
  });
}
