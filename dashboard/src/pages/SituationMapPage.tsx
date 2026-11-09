import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layers, Eye } from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { GlassPanel } from '../components/GlassPanel';
import { StatusBadge } from '../components/StatusBadge';
import { SecondaryButton } from '../components/SecondaryButton';
import { raahatService } from '../services/raahatService';
import type { Incident, Resource } from '../types/raahat';

export function SituationMapPage() {
  const navigate = useNavigate();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [incs, res] = await Promise.all([
        raahatService.getIncidents(),
        raahatService.getResources(),
      ]);
      setIncidents(incs);
      setResources(res);
      if (incs.length > 0) setSelectedIncident(incs[0]);
    } catch (err) {
      console.error('Failed to load map data', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#cbd5e1' }}>
        Loading tactical situation map...
      </div>
    );
  }

  return (
    <div style={{ padding: '1.25rem 1.5rem', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title="Tactical Situation Map"
        subtitle="Uncertainty-aware geospatial intelligence with safety-critical visual encodings"
        actions={
          <SecondaryButton onClick={loadData}>
            <span>↻ Refresh Locations</span>
          </SecondaryButton>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '1.25rem' }}>
        {/* Tactical Canvas & Map Display */}
        <GlassPanel style={{ padding: '1.25rem', position: 'relative', minHeight: 520, display: 'flex', flexDirection: 'column' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 12,
            }}
          >
            <div style={{ fontWeight: 800, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Layers size={16} style={{ color: '#38bdf8' }} />
              <span>Geospatial Safety Encodings & Active Disaster Zone</span>
            </div>

            {/* Safety Legend */}
            <div
              style={{
                display: 'flex',
                gap: 12,
                fontSize: '0.74rem',
                fontFamily: 'monospace',
                background: 'rgba(8, 12, 22, 0.75)',
                padding: '4px 12px',
                borderRadius: 9999,
                border: '1px solid var(--dash-glass-border)',
              }}
            >
              <span style={{ color: '#34d399' }}>● Confirmed</span>
              <span style={{ color: '#38bdf8' }}>○ Candidate</span>
              <span style={{ color: '#fcd34d' }}>◌ Approximate</span>
              <span style={{ color: '#ff8099' }}>▲ Contradictory</span>
            </div>
          </div>

          {/* Interactive Tactical Map Visualizer */}
          <div
            style={{
              flex: 1,
              borderRadius: 12,
              background: 'radial-gradient(ellipse at center, rgba(15, 23, 42, 0.9) 0%, rgba(7, 9, 14, 0.98) 100%)',
              border: '1px solid var(--dash-glass-border)',
              position: 'relative',
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {/* Grid Lines Pattern */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                backgroundImage:
                  'linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px)',
                backgroundSize: '40px 40px',
                pointerEvents: 'none',
              }}
            />

            {/* Tactical Incident Markers */}
            <div
              style={{
                position: 'absolute',
                inset: '40px',
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                justifyContent: 'space-around',
                gap: 20,
              }}
            >
              {incidents.slice(0, 6).map((inc, i) => {
                const isSelected = selectedIncident?.id === inc.id;
                const isP0 = (inc.operational_priority || '').toLowerCase().includes('p0') ||
                             (inc.operational_priority || '').toLowerCase().includes('critical');

                return (
                  <div
                    key={inc.id}
                    onClick={() => setSelectedIncident(inc)}
                    style={{
                      cursor: 'pointer',
                      padding: '12px 16px',
                      borderRadius: 10,
                      background: isSelected
                        ? 'rgba(56, 189, 248, 0.25)'
                        : isP0
                        ? 'rgba(255, 51, 102, 0.18)'
                        : 'rgba(15, 23, 42, 0.75)',
                      border: isSelected
                        ? '2px solid #38bdf8'
                        : isP0
                        ? '1px solid #ff3366'
                        : '1px solid var(--dash-glass-border)',
                      boxShadow: isP0
                        ? '0 0 20px rgba(255, 51, 102, 0.35)'
                        : '0 4px 14px rgba(0,0,0,0.4)',
                      transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                      minWidth: 180,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontSize: '0.7rem', fontWeight: 800, color: isP0 ? '#ff8099' : '#38bdf8' }}>
                        ZONE-{i + 1}
                      </span>
                      <StatusBadge status={inc.operational_priority} showIcon={false} />
                    </div>
                    <div style={{ fontWeight: 700, color: '#f8fafc', fontSize: '0.85rem' }}>
                      📍 {inc.hypotheses?.[0]?.candidate_label || `Incident ${inc.id.slice(0, 8)}`}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--dash-text-muted)', marginTop: 4 }}>
                      👥 {inc.severity_facts?.people_count || 1} victims · {inc.severity_facts?.trapped_status ? 'Trapped' : 'Open'}
                    </div>
                  </div>
                );
              })}
            </div>

            <div
              style={{
                position: 'absolute',
                bottom: 12,
                left: 12,
                fontSize: '0.72rem',
                fontFamily: 'monospace',
                color: 'var(--dash-text-muted)',
                background: 'rgba(7, 9, 14, 0.8)',
                padding: '4px 10px',
                borderRadius: 4,
              }}
            >
              POSTGIS SPATIAL PROJECTION: EPSG:4326 · ACTIVE DISASTER BOUNDS
            </div>
          </div>
        </GlassPanel>

        {/* Selected Incident Inspector Sidebar */}
        <GlassPanel style={{ padding: '1.25rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#f8fafc', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Eye size={18} style={{ color: '#38bdf8' }} />
            <span>Pin Details</span>
          </h3>

          {selectedIncident ? (
            <div>
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--dash-text-muted)' }}>
                  INCIDENT IDENTIFIER
                </div>
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#38bdf8', marginTop: 2 }}>
                  {selectedIncident.id}
                </div>
              </div>

              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--dash-text-muted)' }}>
                  ASSESSED PRIORITY
                </div>
                <div style={{ marginTop: 4 }}>
                  <StatusBadge status={selectedIncident.operational_priority} />
                </div>
              </div>

              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--dash-text-muted)' }}>
                  HEADCOUNT & TRAPPED
                </div>
                <div style={{ fontWeight: 700, color: '#f8fafc', fontSize: '0.95rem', marginTop: 2 }}>
                  👥 {selectedIncident.severity_facts?.people_count || 1} persons ·{' '}
                  <span style={{ color: selectedIncident.severity_facts?.trapped_status ? '#ff8099' : '#34d399' }}>
                    {selectedIncident.severity_facts?.trapped_status ? 'Trapped on Roof' : 'Ground Level'}
                  </span>
                </div>
              </div>

              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--dash-text-muted)' }}>
                  WATER STATUS
                </div>
                <div style={{ color: '#38bdf8', fontSize: '0.88rem', fontWeight: 600, marginTop: 2 }}>
                  {selectedIncident.severity_facts?.water_level_trend
                    ? `🌊 ${selectedIncident.severity_facts.water_level_trend.toUpperCase()}`
                    : 'Stable / Not reported'}
                </div>
              </div>

              <div style={{ marginTop: 20 }}>
                <SecondaryButton
                  style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => navigate(`/incidents/${selectedIncident.id}`)}
                >
                  Open Full Dossier →
                </SecondaryButton>
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--dash-text-muted)', fontSize: '0.85rem' }}>
              Select an incident pin on the map to inspect details.
            </div>
          )}

          <div style={{ marginTop: '2rem', borderTop: '1px solid var(--dash-glass-border)', paddingTop: 14 }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#f8fafc', marginBottom: 8 }}>
              Nearby Rescue Assets:
            </div>
            {resources.slice(0, 3).map((r) => (
              <div
                key={r.id}
                style={{
                  fontSize: '0.78rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginBottom: 6,
                  color: 'var(--dash-text-secondary)',
                }}
              >
                <span>🛡️ {r.name}</span>
                <span style={{ color: '#34d399', fontWeight: 700 }}>{r.availability_status}</span>
              </div>
            ))}
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
