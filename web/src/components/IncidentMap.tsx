/**
 * Operational map. Loaded lazily (Leaflet is the largest dependency).
 *
 * Draws only what has a recorded position. Incidents whose position is a
 * candidate are drawn with a dashed uncertainty ring; confirmed positions with
 * a solid one. Resource markers grey out when their position is older than
 * two hours. Nothing is placed by guess.
 */
import 'leaflet/dist/leaflet.css';

import L from 'leaflet';
import { useEffect, useMemo, useRef } from 'react';

import { config } from '../lib/config';
import { formatAge } from '../lib/format';
import { PRIORITY } from '../lib/labels';
import type { Coordinates, IncidentSummary, LocationCandidate, Resource } from '../lib/types';

const STALE_POSITION_MS = 2 * 60 * 60 * 1000;
const PRIORITY_COLOR: Record<string, string> = {
  critical_review: '#b42318', urgent: '#c4520a', unassessed: '#8a5a00', standard: '#3d5a80', low: '#6b747b',
};

export interface IncidentMapProps {
  incidents: IncidentSummary[];
  resources?: Resource[];
  candidates?: LocationCandidate[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  center?: Coordinates | null;
  picking?: boolean;
  onPick?: (point: Coordinates) => void;
  label?: string;
  legendOpen?: boolean;
}

function markerHtml(incident: IncidentSummary, selected: boolean): string {
  const letter = PRIORITY[incident.priority].label.charAt(0);
  const candidate = incident.location.status !== 'confirmed';
  return `<div class="marker marker-${incident.priority}" data-selected="${selected}" data-candidate="${candidate}"><span>${letter === 'N' ? '?' : letter}</span></div>`;
}

export default function IncidentMap({
  incidents, resources = [], candidates = [], selectedId, onSelect, center, picking, onPick, label = 'Incident map', legendOpen = typeof window === 'undefined' || window.innerWidth > 900,
}: IncidentMapProps) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layers = useRef<L.LayerGroup | null>(null);
  const fitted = useRef(false);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;

  const located = useMemo(() => incidents.filter((i) => i.location.coordinates), [incidents]);

  useEffect(() => {
    if (!element.current || map.current) return;
    const instance = L.map(element.current, { zoomControl: true, attributionControl: true, preferCanvas: false });
    L.tileLayer(config.mapTileUrl, { attribution: config.mapAttribution, maxZoom: 19 }).addTo(instance);
    instance.setView(center ? [center.latitude, center.longitude] : [10.0, 76.3], center ? 11 : 7);
    layers.current = L.layerGroup().addTo(instance);
    instance.on('click', (event: L.LeafletMouseEvent) => {
      pickRef.current?.({ latitude: event.latlng.lat, longitude: event.latlng.lng });
    });
    map.current = instance;
    const observer = new ResizeObserver(() => instance.invalidateSize());
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      instance.remove();
      map.current = null;
    };
    // The map is created once; later prop changes are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    instance.getContainer().style.cursor = picking ? 'crosshair' : '';
  }, [picking]);

  useEffect(() => {
    const group = layers.current;
    const instance = map.current;
    if (!group || !instance) return;
    group.clearLayers();
    const now = Date.now();

    for (const incident of located) {
      const { latitude, longitude } = incident.location.coordinates!;
      const selected = incident.id === selectedId;
      const radius = incident.location.uncertainty_radius_m;
      if (radius && (selected || radius < 3000)) {
        L.circle([latitude, longitude], {
          radius,
          color: PRIORITY_COLOR[incident.priority],
          weight: selected ? 2 : 1,
          opacity: 0.7,
          fillOpacity: selected ? 0.08 : 0.04,
          dashArray: incident.location.status === 'confirmed' ? undefined : '6 6',
          interactive: false,
        }).addTo(group);
      }
      const marker = L.marker([latitude, longitude], {
        icon: L.divIcon({ html: markerHtml(incident, selected), className: '', iconSize: [28, 28], iconAnchor: [14, 14] }),
        keyboard: true,
        title: `${incident.reference} · ${PRIORITY[incident.priority].label}`,
        alt: `${incident.reference}, ${PRIORITY[incident.priority].label}`,
        zIndexOffset: selected ? 1000 : 1000 - PRIORITY[incident.priority].rank * 100,
        riseOnHover: true,
      });
      marker.bindTooltip(
        `<strong>${incident.reference}</strong> · ${PRIORITY[incident.priority].label}<br>${
          incident.location.status === 'confirmed' ? 'Confirmed position' : 'Unconfirmed position'
        }${incident.location.label ? `: ${escapeHtml(incident.location.label)}` : ''}`,
        { direction: 'top', offset: [0, -12] },
      );
      marker.on('click', () => selectRef.current?.(incident.id));
      marker.addTo(group);
    }

    for (const candidate of candidates) {
      if (candidate.verification_status === 'rejected' || candidate.is_current) continue;
      const { latitude, longitude } = candidate.coordinates;
      L.circleMarker([latitude, longitude], { radius: 6, color: '#6941c6', weight: 2, fillOpacity: 0.2, dashArray: '3 3' })
        .bindTooltip(`Candidate: ${escapeHtml(candidate.label ?? 'unnamed')}`)
        .addTo(group);
      if (candidate.uncertainty_radius_m) {
        L.circle([latitude, longitude], {
          radius: candidate.uncertainty_radius_m, color: '#6941c6', weight: 1, dashArray: '4 6', fillOpacity: 0.03, interactive: false,
        }).addTo(group);
      }
    }

    for (const resource of resources) {
      if (!resource.position) continue;
      const age = now - Date.parse(resource.position.reported_at);
      const stale = age > STALE_POSITION_MS;
      L.marker([resource.position.coordinates.latitude, resource.position.coordinates.longitude], {
        icon: L.divIcon({
          html: `<div class="marker marker-resource" data-stale="${stale}"><span>${escapeHtml(resource.callsign.slice(0, 2))}</span></div>`,
          className: '', iconSize: [24, 24], iconAnchor: [12, 12],
        }),
        title: `${resource.callsign}, position ${formatAge(resource.position.reported_at)} old`,
        zIndexOffset: -500,
      })
        .bindTooltip(
          `<strong>${escapeHtml(resource.callsign)}</strong> · ${escapeHtml(resource.name)}<br>Position reported ${formatAge(
            resource.position.reported_at,
          )} ago (${escapeHtml(resource.position.source ?? 'unknown source')})${stale ? '<br><em>May be out of date</em>' : ''}`,
        )
        .addTo(group);
    }

    if (!fitted.current && located.length) {
      const bounds = L.latLngBounds(located.map((i) => [i.location.coordinates!.latitude, i.location.coordinates!.longitude]));
      instance.fitBounds(bounds.pad(0.3), { maxZoom: 14 });
      fitted.current = true;
    }
  }, [located, resources, candidates, selectedId]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !selectedId) return;
    const incident = located.find((i) => i.id === selectedId);
    if (incident) {
      const { latitude, longitude } = incident.location.coordinates!;
      instance.panTo([latitude, longitude], { animate: !window.matchMedia('(prefers-reduced-motion: reduce)').matches });
    }
  }, [selectedId, located]);

  const missing = incidents.length - located.length;
  return (
    <div className="map-host" style={{ position: 'relative', height: '100%' }}>
      <div ref={element} className="map" role="application" aria-label={label} />
      <details className="map-overlay map-legend" open={legendOpen}>
        <summary>Legend</summary>
        <div className="legend-items">
        <span className="row"><span className="marker marker-critical_review" style={{ width: 12, height: 12, border: 0 }} /> Critical</span>
        <span className="row"><span className="marker marker-urgent" style={{ width: 12, height: 11, padding: 0 }} /> Urgent</span>
        <span className="row"><span className="marker marker-unassessed" style={{ width: 12, height: 12, borderWidth: 1 }} /> Not assessed</span>
        <span className="row"><span className="marker marker-standard" style={{ width: 12, height: 12, border: 0 }} /> Standard / low</span>
        <span className="row"><span className="marker marker-resource" style={{ width: 12, height: 12, borderWidth: 1 }} /> Resource</span>
        <span className="faint">Dashed ring: unconfirmed position</span>
        </div>
      </details>
      {(missing > 0 || picking) && (
        <div className="map-overlay map-note" role="status">
          {picking ? (
            <strong>Click the map to set the position.</strong>
          ) : (
            <>
              <strong className="num">{missing}</strong> incident{missing === 1 ? ' has' : 's have'} no established position and {missing === 1 ? 'is' : 'are'} not shown.
            </>
          )}
        </div>
      )}
    </div>
  );
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}
