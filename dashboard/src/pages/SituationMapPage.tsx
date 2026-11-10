import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MapContainer,
  TileLayer,
  Marker,
  Circle,
  Popup,
  useMap,
} from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {
  Eye,
  Crosshair,
  Shield,
  Layers,
  Filter,
  RefreshCw,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { PageHeader } from '../components/PageHeader';
import { GlassPanel } from '../components/GlassPanel';
import { StatusBadge } from '../components/StatusBadge';
import { SecondaryButton } from '../components/SecondaryButton';
import { PrimaryButton } from '../components/PrimaryButton';
import { raahatService } from '../services/raahatService';
import type { Incident, Resource } from '../types/raahat';
import {
  calculateDistanceKm,
  DEOC_COVERAGE_RADIUS_KM,
  SEOC_COVERAGE_RADIUS_KM,
} from '../utils/geoUtils';

// ── Leaflet Dynamic View Controller ─────────────────────────────────────────
function MapViewController({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo(center, zoom, { duration: 1.2 });
  }, [center, zoom, map]);
  return null;
}

// ── Custom SVG Pin Builders ─────────────────────────────────────────────────
function getIncidentMarkerIcon(priority: string, isTrapped: boolean) {
  const prio = priority.toLowerCase();
  const isP0 = prio === 'critical_review' || prio === 'p0';
  const isP1 = prio === 'urgent' || prio === 'p1';
  const isP2 = prio === 'moderate' || prio === 'p2';

  const color = isP0 ? '#ff3366' : isP1 ? '#f59e0b' : isP2 ? '#38bdf8' : '#94a3b8';
  const pulseHtml = isP0 || isTrapped
    ? `<div style="position:absolute;inset:-8px;border-radius:50%;border:2px solid ${color};animation:leaflet-pulse 1.8s cubic-bezier(0,0,0.2,1) infinite;opacity:0.8;"></div>`
    : '';

  return L.divIcon({
    className: 'tactical-map-pin',
    html: `
      <div style="position:relative;width:32px;height:32px;display:flex;align-items:center;justify-content:center;">
        ${pulseHtml}
        <div style="width:26px;height:26px;border-radius:50%;background:${color};border:2px solid #ffffff;box-shadow:0 0 14px ${color};display:flex;align-items:center;justify-content:center;color:#ffffff;font-size:11px;font-weight:900;font-family:sans-serif;">
          ${isP0 ? '!' : isTrapped ? '⚠️' : '●'}
        </div>
      </div>
    `,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -18],
  });
}

function getResourceMarkerIcon(availability: string) {
  const isAvail = availability.toLowerCase() === 'available';
  const color = isAvail ? '#10b981' : '#3b82f6';

  return L.divIcon({
    className: 'resource-map-pin',
    html: `
      <div style="width:26px;height:26px;border-radius:6px;background:${color};border:2px solid #ffffff;box-shadow:0 0 10px ${color};display:flex;align-items:center;justify-content:center;font-size:12px;">
        🛡️
      </div>
    `,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -14],
  });
}

export function SituationMapPage() {
  const navigate = useNavigate();
  const { session } = useAuth();

  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);

  // Map controls
  const [showUncertaintyCircles, setShowUncertaintyCircles] = useState<boolean>(true);
  const [showResources, setShowResources] = useState<boolean>(true);
  const [filterP0Only, setFilterP0Only] = useState<boolean>(false);

  // Default coordinate center based on active authenticated jurisdiction
  const districtCenter: [number, number] = useMemo(() => {
    if (session?.center_lat && session?.center_lng) {
      return [session.center_lat, session.center_lng];
    }
    // Default to Kerala / Ernakulam
    return [10.1076, 76.3516];
  }, [session]);

  const defaultZoom = session?.zoom || 11;
  const [mapCenter, setMapCenter] = useState<[number, number]>(districtCenter);
  const [mapZoom, setMapZoom] = useState<number>(defaultZoom);

  // Sync center when district changes
  useEffect(() => {
    setMapCenter(districtCenter);
    setMapZoom(defaultZoom);
  }, [districtCenter, defaultZoom]);

  const loadData = useCallback(async () => {
    try {
      const [incs, res] = await Promise.all([
        raahatService.getIncidentsWithLocations(),
        raahatService.getResources(),
      ]);
      setIncidents(incs);
      setResources(res);
    } catch (err) {
      console.error('Failed to load situation map data', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // District/State-scoped incident filtering:
  // Only display incidents whose geocoded hypotheses fall within the authenticated jurisdiction radius.
  const visibleIncidents = useMemo(() => {
    const maxRadius = session?.district_code
      ? DEOC_COVERAGE_RADIUS_KM
      : SEOC_COVERAGE_RADIUS_KM;

    return incidents.filter((inc) => {
      if (filterP0Only) {
        const p = (inc.operational_priority || '').toLowerCase();
        if (p !== 'critical_review' && p !== 'p0') return false;
      }

      // Check incident coordinates distance from current jurisdiction center
      const hyp = inc.hypotheses?.[0];
      if (!hyp?.coordinates) {
        // Incident has no resolved coordinate: do not display on tactical map for unrelated jurisdiction
        return false;
      }

      const dist = calculateDistanceKm(
        districtCenter[0],
        districtCenter[1],
        hyp.coordinates.latitude,
        hyp.coordinates.longitude
      );

      return dist <= maxRadius;
    });
  }, [incidents, filterP0Only, districtCenter, session]);

  // District/State-scoped resource filtering:
  // Only show rescue assets based within this DEOC/SEOC operational grid
  const visibleResources = useMemo(() => {
    if (!showResources) return [];

    const maxRadius = session?.district_code
      ? DEOC_COVERAGE_RADIUS_KM
      : SEOC_COVERAGE_RADIUS_KM;

    return resources.filter((res) => {
      if (!res.location?.latitude || !res.location?.longitude) return false;

      const dist = calculateDistanceKm(
        districtCenter[0],
        districtCenter[1],
        res.location.latitude,
        res.location.longitude
      );

      return dist <= maxRadius;
    });
  }, [resources, showResources, districtCenter, session]);

  // Keep selected incident synchronized with visible incidents in this sector
  useEffect(() => {
    if (visibleIncidents.length > 0) {
      if (!selectedIncident || !visibleIncidents.some((i) => i.id === selectedIncident.id)) {
        setSelectedIncident(visibleIncidents[0]);
      }
    } else {
      setSelectedIncident(null);
    }
  }, [visibleIncidents, selectedIncident]);

  const handleRecenterDistrict = () => {
    setMapCenter(districtCenter);
    setMapZoom(defaultZoom);
  };

  if (loading) {
    return (
      <div
        style={{
          padding: '4rem 2rem',
          textAlign: 'center',
          color: '#cbd5e1',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 16,
        }}
      >
        <div style={{ animation: 'spin 1.5s linear infinite' }}>
          <RefreshCw size={28} style={{ color: '#38bdf8' }} />
        </div>
        <div style={{ fontSize: '1rem', fontWeight: 700 }}>
          Initializing Real-time Geospatial Intelligence Grid...
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '1.25rem 1.5rem', maxWidth: 1560, margin: '0 auto' }}>
      <PageHeader
        title="Tactical Situation Map"
        subtitle={`Live GIS Emergency Grid · ${session?.district_name || session?.state_name || 'National Command'} (EPSG:4326 WGS-84)`}
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <SecondaryButton onClick={handleRecenterDistrict}>
              <Crosshair size={14} />
              <span>Recenter District</span>
            </SecondaryButton>
            <SecondaryButton onClick={loadData}>
              <RefreshCw size={14} />
              <span>Refresh Coordinates</span>
            </SecondaryButton>
          </div>
        }
      />

      {/* Control Strip & Visual Encoding Safety Legend */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '10px 16px',
          background: 'rgba(10, 16, 30, 0.75)',
          borderRadius: 10,
          border: '1px solid var(--dash-glass-border)',
          marginBottom: '1rem',
          backdropFilter: 'blur(12px)',
        }}
      >
        {/* Layer Toggles */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontSize: '0.78rem', fontWeight: 800, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 5 }}>
            <Layers size={14} style={{ color: '#38bdf8' }} />
            LAYERS:
          </span>

          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: '#f8fafc', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showUncertaintyCircles}
              onChange={(e) => setShowUncertaintyCircles(e.target.checked)}
            />
            <span>Uncertainty Radii (m)</span>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: '#f8fafc', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showResources}
              onChange={(e) => setShowResources(e.target.checked)}
            />
            <span>Rescue Units ({resources.length})</span>
          </label>

          <button
            onClick={() => setFilterP0Only(!filterP0Only)}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              background: filterP0Only ? 'rgba(255, 51, 102, 0.25)' : 'rgba(255, 255, 255, 0.05)',
              border: `1px solid ${filterP0Only ? '#ff3366' : 'rgba(255, 255, 255, 0.1)'}`,
              color: filterP0Only ? '#ff8099' : '#cbd5e1',
              fontSize: '0.76rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
          >
            <Filter size={12} />
            <span>P0 Critical Only</span>
          </button>
        </div>

        {/* Safety Encoding Legend */}
        <div
          style={{
            display: 'flex',
            gap: 12,
            fontSize: '0.72rem',
            fontFamily: 'monospace',
            color: '#cbd5e1',
          }}
        >
          <span style={{ color: '#ff3366', fontWeight: 800 }}>● P0 Critical</span>
          <span style={{ color: '#f59e0b' }}>● P1 Urgent</span>
          <span style={{ color: '#38bdf8' }}>● P2 Moderate</span>
          <span style={{ color: '#10b981' }}>◌ Verified ±r</span>
          <span style={{ color: '#34d399' }}>🛡️ Unit Available</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '1.25rem' }}>
        {/* Main Real Leaflet Map */}
        <GlassPanel
          style={{
            padding: 0,
            overflow: 'hidden',
            minHeight: 640,
            height: '75vh',
            position: 'relative',
            borderRadius: 14,
            border: '1px solid var(--dash-glass-border)',
          }}
        >
          <MapContainer
            center={districtCenter}
            zoom={defaultZoom}
            style={{ width: '100%', height: '100%', background: '#070a13' }}
            zoomControl={true}
          >
            <MapViewController center={mapCenter} zoom={mapZoom} />

            {/* Keyless OpenStreetMap Tile Layer with Tactical Night-Ops Filter */}
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              maxZoom={19}
              className="tactical-dark-tiles"
            />

            {/* Plot Incident Markers & Uncertainty Circles */}
            {visibleIncidents.map((inc) => {
              const hyp = inc.hypotheses?.[0];
              if (!hyp?.coordinates) return null;
              const lat = hyp.coordinates.latitude;
              const lng = hyp.coordinates.longitude;
              const radiusM = hyp?.uncertainty_radius_m || 350;

              const priority = inc.operational_priority || 'unassessed';
              const isTrapped = Boolean(inc.severity_facts?.trapped_status);
              const markerIcon = getIncidentMarkerIcon(priority, isTrapped);

              return (
                <div key={inc.id}>
                  {/* Uncertainty radius circle */}
                  {showUncertaintyCircles && (
                    <Circle
                      center={[lat, lng]}
                      radius={radiusM}
                      pathOptions={{
                        color: isTrapped ? '#ff3366' : '#38bdf8',
                        fillColor: isTrapped ? '#ff3366' : '#38bdf8',
                        fillOpacity: 0.12,
                        weight: 1.5,
                        dashArray: '6, 6',
                      }}
                    />
                  )}

                  {/* Marker Pin */}
                  <Marker
                    position={[lat, lng]}
                    icon={markerIcon}
                    eventHandlers={{
                      click: () => {
                        setSelectedIncident(inc);
                      },
                    }}
                  >
                    <Popup className="tactical-leaflet-popup">
                      <div style={{ minWidth: 230, color: '#f8fafc', padding: '4px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                          <span style={{ fontSize: '0.72rem', fontFamily: 'monospace', color: '#38bdf8', fontWeight: 800 }}>
                            INCIDENT #{inc.id.slice(0, 8)}
                          </span>
                          <StatusBadge status={priority} />
                        </div>

                        <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#ffffff', marginBottom: 4 }}>
                          {hyp?.candidate_label || 'Tactical Sector Incident'}
                        </div>

                        <div style={{ fontSize: '0.75rem', color: '#cbd5e1', marginBottom: 4 }}>
                          👥 <strong>{inc.severity_facts?.people_count || 1} persons</strong> ·{' '}
                          <span style={{ color: isTrapped ? '#ff8099' : '#34d399', fontWeight: 700 }}>
                            {isTrapped ? 'Trapped' : 'Open Ground'}
                          </span>
                        </div>

                        {inc.severity_facts?.water_level_trend && (
                          <div style={{ fontSize: '0.74rem', color: '#38bdf8', marginBottom: 6 }}>
                            🌊 Water Trend: <strong>{inc.severity_facts.water_level_trend.toUpperCase()}</strong>
                          </div>
                        )}

                        <div style={{ fontSize: '0.7rem', color: '#94a3b8', fontFamily: 'monospace', marginBottom: 8 }}>
                          GPS: {lat.toFixed(4)}° N, {lng.toFixed(4)}° E (±{Math.round(radiusM)}m)
                        </div>

                        <button
                          onClick={() => navigate(`/incidents/${inc.id}`)}
                          style={{
                            width: '100%',
                            padding: '6px 10px',
                            borderRadius: 6,
                            background: '#0284c7',
                            color: '#ffffff',
                            border: 'none',
                            fontSize: '0.76rem',
                            fontWeight: 800,
                            cursor: 'pointer',
                          }}
                        >
                          Open Incident Dossier →
                        </button>
                      </div>
                    </Popup>
                  </Marker>
                </div>
              );
            })}

            {/* Plot Rescue Units */}
            {visibleResources.map((res) => {
              if (!res.location?.latitude || !res.location?.longitude) return null;
              const lat = res.location.latitude;
              const lng = res.location.longitude;
              const icon = getResourceMarkerIcon(res.availability_status);

                return (
                  <Marker key={res.id} position={[lat, lng]} icon={icon}>
                    <Popup className="tactical-leaflet-popup">
                      <div style={{ minWidth: 200, color: '#f8fafc', padding: '4px' }}>
                        <div style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 800, textTransform: 'uppercase' }}>
                          Rescue Asset · {res.resource_type}
                        </div>
                        <div style={{ fontSize: '0.88rem', fontWeight: 800, color: '#ffffff', margin: '2px 0 4px' }}>
                          {res.name}
                        </div>
                        <div style={{ fontSize: '0.76rem', color: '#cbd5e1' }}>
                          Status: <strong style={{ color: '#34d399' }}>{res.availability_status.toUpperCase()}</strong>
                        </div>
                        <div style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: 2 }}>
                          Crew Capacity: {res.capacity} personnel
                        </div>
                      </div>
                    </Popup>
                  </Marker>
                );
              })}
          </MapContainer>

          {/* Active Jurisdiction Tactical HUD Chip */}
          <div
            style={{
              position: 'absolute',
              top: 14,
              left: 54,
              zIndex: 1000,
              background: 'rgba(9, 14, 26, 0.88)',
              border: '1px solid rgba(255, 255, 255, 0.16)',
              borderRadius: 8,
              padding: '6px 14px',
              backdropFilter: 'blur(10px)',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            }}
          >
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: '#10b981',
                boxShadow: '0 0 10px #10b981',
              }}
            />
            <div style={{ fontSize: '0.78rem' }}>
              <span style={{ fontWeight: 800, color: '#ffffff' }}>
                {session?.district_name ? `DEOC ${session.district_name.toUpperCase()}` : 'STATE EOC COMMAND'}
              </span>
              <span style={{ color: '#94a3b8', marginLeft: 8, fontFamily: 'monospace' }}>
                [{districtCenter[0].toFixed(4)}°N, {districtCenter[1].toFixed(4)}°E]
              </span>
            </div>
          </div>
        </GlassPanel>

        {/* Selected Incident Tactical Dossier Inspector */}
        <GlassPanel style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column' }}>
          <h3
            style={{
              fontSize: '1.05rem',
              fontWeight: 900,
              color: '#f8fafc',
              marginBottom: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Eye size={18} style={{ color: '#38bdf8' }} />
            <span>Target Inspector</span>
          </h3>

          {selectedIncident ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, flex: 1 }}>
              <div>
                <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--dash-text-muted)' }}>
                  INCIDENT IDENTIFIER
                </div>
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#38bdf8', marginTop: 2 }}>
                  {selectedIncident.id}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--dash-text-muted)' }}>
                  ASSESSED OPERATIONAL PRIORITY
                </div>
                <div style={{ marginTop: 4 }}>
                  <StatusBadge status={selectedIncident.operational_priority} />
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--dash-text-muted)' }}>
                  HEADCOUNT & SURVIVAL STATUS
                </div>
                <div style={{ fontWeight: 800, color: '#f8fafc', fontSize: '0.96rem', marginTop: 2 }}>
                  👥 {selectedIncident.severity_facts?.people_count || 1} people ·{' '}
                  <span
                    style={{
                      color: selectedIncident.severity_facts?.trapped_status ? '#ff8099' : '#34d399',
                    }}
                  >
                    {selectedIncident.severity_facts?.trapped_status ? 'TRAPPED (ROOF/UPPER)' : 'GROUND LEVEL'}
                  </span>
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--dash-text-muted)' }}>
                  WATER STATUS & HAZARDS
                </div>
                <div style={{ color: '#38bdf8', fontSize: '0.88rem', fontWeight: 700, marginTop: 2 }}>
                  {selectedIncident.severity_facts?.water_level_trend
                    ? `🌊 ${selectedIncident.severity_facts.water_level_trend.toUpperCase()}`
                    : 'Stable water level'}
                </div>
              </div>

              {selectedIncident.severity_facts?.relief_needs && (
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--dash-text-muted)', marginBottom: 4 }}>
                    RELIEF REQUIREMENTS
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {selectedIncident.severity_facts.relief_needs.map((need) => (
                      <span
                        key={need}
                        style={{
                          fontSize: '0.72rem',
                          padding: '2px 8px',
                          borderRadius: 4,
                          background: 'rgba(56, 189, 248, 0.15)',
                          color: '#38bdf8',
                          border: '1px solid rgba(56, 189, 248, 0.3)',
                          fontWeight: 700,
                        }}
                      >
                        {need}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ marginTop: 12 }}>
                <PrimaryButton
                  style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => navigate(`/incidents/${selectedIncident.id}`)}
                >
                  Inspect Incident Dossier →
                </PrimaryButton>
              </div>

              {/* Nearest Deployable Units */}
              <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--dash-glass-border)', paddingTop: 14 }}>
                <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#f8fafc', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Shield size={14} style={{ color: '#34d399' }} />
                  <span>Sector Rescue Assets</span>
                </div>
                {visibleResources.length === 0 ? (
                  <div style={{ fontSize: '0.76rem', color: '#64748b', fontStyle: 'italic', padding: '6px 0' }}>
                    No rescue units deployed in this sector perimeter.
                  </div>
                ) : (
                  visibleResources.slice(0, 4).map((r) => (
                    <div
                      key={r.id}
                      style={{
                        fontSize: '0.76rem',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 8,
                        padding: '6px 8px',
                        borderRadius: 6,
                        background: 'rgba(255, 255, 255, 0.03)',
                      }}
                    >
                      <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{r.name}</span>
                      <span
                        style={{
                          color: r.availability_status.toLowerCase() === 'available' ? '#34d399' : '#38bdf8',
                          fontWeight: 700,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                        }}
                      >
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
                        {r.availability_status}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--dash-text-muted)', fontSize: '0.85rem' }}>
              Click any incident marker on the map to inspect location telemetry, victim counts, and triage facts.
            </div>
          )}
        </GlassPanel>
      </div>
    </div>
  );
}
