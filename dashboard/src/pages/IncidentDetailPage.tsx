import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  MapPin,
  Radio,
} from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { GlassPanel } from '../components/GlassPanel';
import { StatusBadge } from '../components/StatusBadge';
import { SecondaryButton } from '../components/SecondaryButton';
import { PrimaryButton } from '../components/PrimaryButton';
import { ConfirmationModal } from '../components/ConfirmationModal';
import { ToastNotification } from '../components/ToastNotification';
import { raahatService } from '../services/raahatService';
import type { IncidentDetail, Resource } from '../types/raahat';
import type { ToastMessage } from '../types/dashboard';

export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Dispatch modal
  const [dispatchModalOpen, setDispatchModalOpen] = useState<boolean>(false);
  const [selectedResourceId, setSelectedResourceId] = useState<string>('');
  const [instructions, setInstructions] = useState<string>('Evacuate trapped victims to designated shelter');
  const [dispatching, setDispatching] = useState<boolean>(false);

  // Toasts
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const addToast = (type: 'success' | 'error' | 'info', title: string, message: string) => {
    setToasts((prev) => [
      ...prev,
      { id: Math.random().toString(36).substring(2, 9), type, title, message },
    ]);
  };
  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const loadData = useCallback(async () => {
    if (!id) return;
    try {
      const [d, res] = await Promise.all([
        raahatService.getIncidentDetail(id),
        raahatService.getResources(),
      ]);
      setDetail(d);
      setResources(res);
      const avail = res.find((r) => (r.availability_status || '').toLowerCase() === 'available');
      if (avail) setSelectedResourceId(avail.id);
    } catch (err) {
      console.error('Failed to load incident detail', err);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAuthorizeDispatch = async () => {
    if (!detail || !selectedResourceId) return;

    setDispatching(true);
    try {
      const resp = await raahatService.dispatchResource({
        disaster_id: detail.incident.disaster_id,
        incident_id: detail.incident.id,
        resource_id: selectedResourceId,
        instructions,
      });

      addToast(
        'success',
        'Rescue Dispatched',
        `Operation authorized with ID: ${resp.operation_id.slice(0, 8)}...`
      );
      setDispatchModalOpen(false);
      await loadData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Dispatch failed';
      addToast('error', 'Dispatch Error', message);
    } finally {
      setDispatching(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#cbd5e1' }}>
        Loading incident dossier...
      </div>
    );
  }

  if (!detail) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <h2 style={{ color: '#f8fafc' }}>Incident Not Found</h2>
        <SecondaryButton onClick={() => navigate('/')} style={{ marginTop: 12 }}>
          Return to Queue
        </SecondaryButton>
      </div>
    );
  }

  const { incident, hypotheses, linked_report_ids, links } = detail;
  const facts = incident.severity_facts || {};

  return (
    <div style={{ padding: '1.25rem 1.5rem', maxWidth: 1200, margin: '0 auto' }}>
      <button
        type="button"
        onClick={() => navigate('/')}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          background: 'none',
          border: 'none',
          color: 'var(--dash-text-muted)',
          fontSize: '0.85rem',
          cursor: 'pointer',
          marginBottom: 12,
        }}
      >
        <ArrowLeft size={16} />
        <span>Back to Operations Queue</span>
      </button>

      <PageHeader
        title={`Incident Dossier: ${incident.id.slice(0, 8)}...`}
        subtitle={`Disaster ID: ${incident.disaster_id} · Created ${new Date(incident.created_at).toLocaleString()}`}
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <SecondaryButton onClick={loadData}>
              <span>↻ Refresh Dossier</span>
            </SecondaryButton>
            <PrimaryButton
              style={{ background: 'linear-gradient(135deg, #ff3366 0%, #dc2626 100%)' }}
              onClick={() => setDispatchModalOpen(true)}
            >
              <span>⚡ Authorize Rescue Unit</span>
            </PrimaryButton>
          </div>
        }
      />

      {/* Top Facts Cards Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <GlassPanel style={{ padding: '1.1rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--dash-text-muted)', marginBottom: 4 }}>
            OPERATIONAL PRIORITY
          </div>
          <div style={{ marginTop: 4 }}>
            <StatusBadge status={incident.operational_priority} />
          </div>
        </GlassPanel>

        <GlassPanel style={{ padding: '1.1rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--dash-text-muted)', marginBottom: 4 }}>
            TOTAL VICTIMS
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#f8fafc', fontFamily: 'monospace' }}>
            👥 {facts.people_count || 1} individuals
          </div>
        </GlassPanel>

        <GlassPanel style={{ padding: '1.1rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--dash-text-muted)', marginBottom: 4 }}>
            TRAPPED STATUS
          </div>
          <div
            style={{
              fontSize: '1.1rem',
              fontWeight: 800,
              color: facts.trapped_status ? '#ff8099' : '#34d399',
            }}
          >
            {facts.trapped_status ? '⚠️ TRAPPED ON ROOF / DEBRIS' : '✓ Safe / Unconfined'}
          </div>
        </GlassPanel>

        <GlassPanel style={{ padding: '1.1rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--dash-text-muted)', marginBottom: 4 }}>
            WATER LEVEL TREND
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#38bdf8' }}>
            {facts.water_level_trend ? `🌊 ${facts.water_level_trend.toUpperCase()}` : 'STABLE / UNKNOWN'}
          </div>
        </GlassPanel>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1.25rem', marginBottom: '1.5rem' }}>
        {/* Left Column: Location Hypotheses & Disambiguation */}
        <GlassPanel style={{ padding: '1.25rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#f8fafc', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <MapPin size={18} style={{ color: '#38bdf8' }} />
            <span>Geospatial Hypotheses & Active Disambiguation</span>
          </h3>

          {hypotheses.length === 0 ? (
            <div style={{ color: 'var(--dash-text-muted)', fontSize: '0.88rem' }}>
              No resolved landmark hypotheses available.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {hypotheses.map((hyp) => (
                <div
                  key={hyp.id}
                  style={{
                    padding: '12px 14px',
                    borderRadius: 8,
                    background: 'rgba(8, 12, 22, 0.65)',
                    border: '1px solid var(--dash-glass-border)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontWeight: 700, color: '#f8fafc', fontSize: '0.95rem' }}>
                      📍 {hyp.candidate_label}
                    </div>
                    <span
                      style={{
                        fontSize: '0.72rem',
                        padding: '2px 8px',
                        borderRadius: 9999,
                        background: 'rgba(56, 189, 248, 0.15)',
                        color: '#38bdf8',
                        fontWeight: 700,
                      }}
                    >
                      {hyp.verification_status}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--dash-text-muted)', marginTop: 6, fontFamily: 'monospace' }}>
                    Coordinates: {hyp.coordinates.latitude.toFixed(5)}, {hyp.coordinates.longitude.toFixed(5)}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 2 }}>
                    Uncertainty Circle: <strong>±{hyp.uncertainty_radius_m}m</strong>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Unknown Fields Invariant */}
          {facts.unknown_fields && facts.unknown_fields.length > 0 && (
            <div style={{ marginTop: '1.25rem' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#f59e0b', marginBottom: 6 }}>
                ⚠️ PRESERVED UNKNOWN FIELDS (Deterministic Safety Policy):
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {facts.unknown_fields.map((f) => (
                  <span
                    key={f}
                    style={{
                      fontSize: '0.72rem',
                      fontFamily: 'monospace',
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: 'rgba(245, 158, 11, 0.15)',
                      color: '#fcd34d',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                    }}
                  >
                    UNKNOWN: {f}
                  </span>
                ))}
              </div>
            </div>
          )}
        </GlassPanel>

        {/* Right Column: Evidence Provenance Graph & Reports */}
        <GlassPanel style={{ padding: '1.25rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#f8fafc', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Radio size={18} style={{ color: '#a855f7' }} />
            <span>Evidence Graph & Linked Signals ({linked_report_ids.length})</span>
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 300, overflowY: 'auto' }}>
            {linked_report_ids.map((repId, idx) => (
              <div
                key={repId}
                style={{
                  padding: '8px 12px',
                  borderRadius: 6,
                  background: 'rgba(8, 12, 22, 0.65)',
                  border: '1px solid var(--dash-glass-border)',
                  fontSize: '0.8rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <span style={{ fontWeight: 700, color: '#38bdf8' }}>Report #{idx + 1}</span>
                  <div style={{ color: 'var(--dash-text-muted)', fontFamily: 'monospace', fontSize: '0.72rem' }}>
                    UUID: {repId}
                  </div>
                </div>
                <span style={{ color: '#10b981', fontWeight: 700, fontSize: '0.75rem' }}>✓ Linked</span>
              </div>
            ))}
          </div>

          {links.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#cbd5e1', marginBottom: 6 }}>
                Incident Entity Links:
              </div>
              {links.map((lnk) => (
                <div
                  key={lnk.id}
                  style={{
                    padding: '8px 10px',
                    borderRadius: 6,
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    fontSize: '0.75rem',
                    color: '#f87171',
                  }}
                >
                  Link type: <strong>{lnk.link_type.toUpperCase()}</strong> · Status: {lnk.status} (Conf:{' '}
                  {Math.round(lnk.confidence * 100)}%)
                </div>
              ))}
            </div>
          )}
        </GlassPanel>
      </div>

      {/* Dispatch Modal */}
      {dispatchModalOpen && (
        <ConfirmationModal
          title="Authorize Rescue Unit Mission"
          description={`Incident ${incident.id.slice(0, 8)}... (${incident.operational_priority.toUpperCase()})`}
          confirmLabel="Sign & Dispatch Unit"
          cancelLabel="Cancel"
          loading={dispatching}
          onConfirm={handleAuthorizeDispatch}
          onCancel={() => setDispatchModalOpen(false)}
        >
          <div style={{ marginTop: 14 }}>
            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, marginBottom: 6, color: '#cbd5e1' }}>
              SELECT AVAILABLE ASSET:
            </label>
            <select
              value={selectedResourceId}
              onChange={(e) => setSelectedResourceId(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 14px',
                borderRadius: 8,
                background: 'rgba(7, 9, 14, 0.9)',
                border: '1px solid var(--dash-glass-border)',
                color: 'white',
                fontSize: '0.88rem',
                marginBottom: 12,
              }}
            >
              <option value="">-- Choose Unit --</option>
              {resources
                .filter((r) => (r.availability_status || '').toLowerCase() === 'available')
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} ({r.resource_type.toUpperCase()} · Cap: {r.capacity})
                  </option>
                ))}
            </select>

            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, marginBottom: 6, color: '#cbd5e1' }}>
              TACTICAL ORDERS:
            </label>
            <textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 14px',
                borderRadius: 8,
                background: 'rgba(7, 9, 14, 0.9)',
                border: '1px solid var(--dash-glass-border)',
                color: 'white',
                fontSize: '0.88rem',
              }}
            />
          </div>
        </ConfirmationModal>
      )}

      <ToastNotification toasts={toasts} onDismiss={removeToast} />
    </div>
  );
}
