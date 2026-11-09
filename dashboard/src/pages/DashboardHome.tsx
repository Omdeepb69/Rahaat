import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Flame,
  Users,
  Radio,
  Shield,
  Search,
  MapPin,
  AlertTriangle,
} from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { MetricCard } from '../components/MetricCard';
import { GlassPanel } from '../components/GlassPanel';
import { StatusBadge } from '../components/StatusBadge';
import { DataTable, type Column } from '../components/DataTable';
import { SecondaryButton } from '../components/SecondaryButton';
import { PrimaryButton } from '../components/PrimaryButton';
import { ConfirmationModal } from '../components/ConfirmationModal';
import { ToastNotification } from '../components/ToastNotification';
import { raahatService } from '../services/raahatService';
import type { Incident, Resource, KPIStats } from '../types/raahat';
import type { ToastMessage } from '../types/dashboard';

export function DashboardHome() {
  const navigate = useNavigate();

  const [metrics, setMetrics] = useState<KPIStats>({
    p0Count: 0,
    trappedCount: 0,
    reportsCount: 0,
    availableResourcesCount: 0,
  });
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Filters & search
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [priorityFilter, setPriorityFilter] = useState<string>('all');
  const [trappedOnly, setTrappedOnly] = useState<boolean>(false);

  // Quick Dispatch Modal
  const [dispatchTargetIncident, setDispatchTargetIncident] = useState<Incident | null>(null);
  const [selectedResourceId, setSelectedResourceId] = useState<string>('');
  const [dispatchInstructions, setDispatchInstructions] = useState<string>('Immediate rescue and evacuation');
  const [dispatching, setDispatching] = useState<boolean>(false);

  // Toast notifications
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
    try {
      const [m, incs, res] = await Promise.all([
        raahatService.getSummaryMetrics(),
        raahatService.getIncidents(),
        raahatService.getResources(),
      ]);
      setMetrics(m);
      setIncidents(incs);
      setResources(res);
    } catch (err) {
      console.error('Failed to load incident command data', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();

    // Listen for live SSE updates
    const unsubscribe = raahatService.connectEventStream((evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (
          payload.type === 'incident.created' ||
          payload.type === 'incident.updated' ||
          payload.type === 'report.received' ||
          payload.type === 'operation.authorized'
        ) {
          loadData();
        }
      } catch {
        loadData();
      }
    });

    return () => {
      unsubscribe();
    };
  }, [loadData]);

  // Filtered incidents
  const filteredIncidents = useMemo(() => {
    return incidents.filter((inc) => {
      if (priorityFilter !== 'all') {
        const prio = (inc.operational_priority || '').toLowerCase();
        if (priorityFilter === 'p0' && prio !== 'critical_review' && prio !== 'p0') return false;
        if (priorityFilter === 'p1' && prio !== 'urgent' && prio !== 'p1') return false;
        if (priorityFilter === 'p2' && prio !== 'moderate' && prio !== 'p2') return false;
        if (priorityFilter === 'p3' && prio !== 'routine' && prio !== 'p3') return false;
      }

      if (trappedOnly && !inc.severity_facts?.trapped_status) {
        return false;
      }

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const idMatch = inc.id.toLowerCase().includes(q);
        const prioMatch = (inc.operational_priority || '').toLowerCase().includes(q);
        const needsMatch = (inc.severity_facts?.relief_needs || []).some((n) =>
          n.toLowerCase().includes(q)
        );
        const labelMatch = (inc.hypotheses || []).some((h) =>
          h.candidate_label.toLowerCase().includes(q)
        );
        return idMatch || prioMatch || needsMatch || labelMatch;
      }

      return true;
    });
  }, [incidents, priorityFilter, trappedOnly, searchQuery]);

  // Handle Quick Dispatch Execution
  const handleAuthorizeDispatch = async () => {
    if (!dispatchTargetIncident || !selectedResourceId) return;

    setDispatching(true);
    try {
      const resp = await raahatService.dispatchResource({
        disaster_id: dispatchTargetIncident.disaster_id,
        incident_id: dispatchTargetIncident.id,
        resource_id: selectedResourceId,
        instructions: dispatchInstructions,
      });

      addToast(
        'success',
        'Rescue Dispatch Authorized',
        `Unit assigned to Incident ${dispatchTargetIncident.id.slice(0, 8)}... (Auth ID: ${resp.operation_id.slice(0, 8)}...)`
      );
      setDispatchTargetIncident(null);
      setSelectedResourceId('');
      await loadData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown dispatch error';
      addToast('error', 'Authorization Failed', message);
    } finally {
      setDispatching(false);
    }
  };

  const columns: Column<Incident>[] = [
    {
      key: 'priority',
      header: 'Priority',
      width: '140px',
      render: (row) => <StatusBadge status={row.operational_priority} />,
    },
    {
      key: 'location',
      header: 'Location / Landmark',
      render: (row) => {
        const topHypothesis = row.hypotheses?.[0];
        const label = topHypothesis?.candidate_label || 'Location Pending Disambiguation';
        const coords = topHypothesis?.coordinates;

        return (
          <div>
            <div style={{ fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 5 }}>
              <MapPin size={14} style={{ color: '#38bdf8' }} />
              <span>{label}</span>
            </div>
            {coords && (
              <div style={{ fontSize: '0.75rem', color: 'var(--dash-text-muted)', fontFamily: 'monospace' }}>
                {coords.latitude.toFixed(4)}, {coords.longitude.toFixed(4)} · ±{topHypothesis?.uncertainty_radius_m || 500}m
              </div>
            )}
          </div>
        );
      },
    },
    {
      key: 'victims',
      header: 'Victims & Status',
      render: (row) => {
        const count = row.severity_facts?.people_count ?? 1;
        const isTrapped = row.severity_facts?.trapped_status;

        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                fontFamily: 'monospace',
                fontWeight: 800,
                fontSize: '0.95rem',
                color: isTrapped ? '#ff8099' : '#f8fafc',
              }}
            >
              👥 {count} {count === 1 ? 'person' : 'people'}
            </span>
            {isTrapped && (
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 800,
                  padding: '2px 8px',
                  borderRadius: 9999,
                  background: 'rgba(255, 51, 102, 0.2)',
                  color: '#ff8099',
                  border: '1px solid rgba(255, 51, 102, 0.4)',
                }}
              >
                TRAPPED
              </span>
            )}
          </div>
        );
      },
    },
    {
      key: 'needs',
      header: 'Needs & Hazards',
      render: (row) => {
        const needs = row.severity_facts?.relief_needs || [];
        const waterTrend = row.severity_facts?.water_level_trend;

        return (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {waterTrend === 'rising' && (
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 800,
                  padding: '2px 7px',
                  borderRadius: 4,
                  background: 'rgba(56, 189, 248, 0.15)',
                  color: '#38bdf8',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                }}
              >
                🌊 Water Rising
              </span>
            )}
            {needs.map((n) => (
              <span
                key={n}
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  padding: '2px 7px',
                  borderRadius: 4,
                  background: 'rgba(15, 23, 42, 0.6)',
                  color: 'var(--dash-text-secondary)',
                  border: '1px solid var(--dash-glass-border)',
                }}
              >
                {n.replace('_', ' ')}
              </span>
            ))}
            {row.severity_facts?.has_contradictions && (
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 800,
                  padding: '2px 7px',
                  borderRadius: 4,
                  background: 'rgba(239, 68, 68, 0.2)',
                  color: '#f87171',
                  border: '1px solid #ef4444',
                }}
              >
                ⚠️ Conflict
              </span>
            )}
          </div>
        );
      },
    },
    {
      key: 'status',
      header: 'Status',
      width: '120px',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      width: '210px',
      render: (row) => (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <SecondaryButton
            style={{ minHeight: 32, padding: '0.25rem 0.75rem', fontSize: '0.78rem' }}
            onClick={() => navigate(`/incidents/${row.id}`)}
          >
            Investigate
          </SecondaryButton>
          <PrimaryButton
            style={{
              minHeight: 32,
              padding: '0.25rem 0.85rem',
              fontSize: '0.78rem',
              background: 'linear-gradient(135deg, #ff3366 0%, #dc2626 100%)',
            }}
            onClick={() => {
              setDispatchTargetIncident(row);
              const available = resources.find((r) => (r.availability_status || '').toLowerCase() === 'available');
              if (available) setSelectedResourceId(available.id);
            }}
          >
            Dispatch
          </PrimaryButton>
        </div>
      ),
    },
  ];

  return (
    <div style={{ padding: '1.25rem 1.5rem', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title="Disaster Operations Command Room"
        subtitle="Multi-agency emergency triage, active landmark disambiguation, and rescue dispatch"
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <SecondaryButton onClick={loadData}>
              <span>↻ Refresh Feed</span>
            </SecondaryButton>
            <PrimaryButton onClick={() => navigate('/operations')}>
              <span>⚡ View Rescue Fleet</span>
            </PrimaryButton>
          </div>
        }
      />

      {/* Live 4-Card KPI Metric Banner */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <MetricCard
          label="P0 CRITICAL EMERGENCIES"
          value={metrics.p0Count}
          deltaLabel="Immediate Rescue Mandate"
          icon={<Flame size={20} style={{ color: '#ff3366' }} />}
          className="metric-card--p0"
          onClick={() => setPriorityFilter('p0')}
        />
        <MetricCard
          label="TRAPPED CITIZENS"
          value={metrics.trappedCount}
          deltaLabel="Reported on Roofs / Debris"
          icon={<Users size={20} style={{ color: '#f59e0b' }} />}
          onClick={() => setTrappedOnly((prev) => !prev)}
        />
        <MetricCard
          label="DISTRESS REPORTS LOGGED"
          value={metrics.reportsCount}
          deltaLabel="IVR, Web SOS, SMS & Radio"
          icon={<Radio size={20} style={{ color: '#06b6d4' }} />}
          onClick={() => navigate('/reports')}
        />
        <MetricCard
          label="AVAILABLE RESCUE UNITS"
          value={metrics.availableResourcesCount}
          deltaLabel="Boats, Ambulances & SDRF"
          icon={<Shield size={20} style={{ color: '#10b981' }} />}
          onClick={() => navigate('/operations')}
        />
      </div>

      {/* Incidents Table Panel */}
      <GlassPanel style={{ padding: '1.25rem' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: '1.25rem',
          }}
        >
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f8fafc' }}>
              Active Incidents Triage Queue
            </h2>
            <div style={{ fontSize: '0.82rem', color: 'var(--dash-text-muted)' }}>
              Showing {filteredIncidents.length} of {incidents.length} incidents
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            {/* Filter Pills */}
            <div
              style={{
                display: 'flex',
                background: 'rgba(8, 12, 22, 0.65)',
                padding: 4,
                borderRadius: 9999,
                border: '1px solid var(--dash-glass-border)',
                gap: 4,
              }}
            >
              {[
                { key: 'all', label: 'All' },
                { key: 'p0', label: 'P0 Critical' },
                { key: 'p1', label: 'P1 Urgent' },
                { key: 'p2', label: 'P2 Moderate' },
              ].map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setPriorityFilter(key)}
                  style={{
                    border: 'none',
                    background: priorityFilter === key ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                    color: priorityFilter === key ? '#38bdf8' : 'var(--dash-text-muted)',
                    fontWeight: 700,
                    fontSize: '0.78rem',
                    padding: '4px 12px',
                    borderRadius: 9999,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Trapped toggle */}
            <button
              type="button"
              onClick={() => setTrappedOnly((prev) => !prev)}
              style={{
                border: trappedOnly ? '1px solid #ff3366' : '1px solid var(--dash-glass-border)',
                background: trappedOnly ? 'rgba(255, 51, 102, 0.2)' : 'rgba(8, 12, 22, 0.65)',
                color: trappedOnly ? '#ff8099' : 'var(--dash-text-muted)',
                fontWeight: 700,
                fontSize: '0.78rem',
                padding: '6px 14px',
                borderRadius: 9999,
                cursor: 'pointer',
              }}
            >
              ⚠️ Trapped Only
            </button>

            {/* Search Box */}
            <div
              style={{
                position: 'relative',
                display: 'flex',
                alignItems: 'center',
                minWidth: 220,
              }}
            >
              <Search
                size={14}
                style={{
                  position: 'absolute',
                  left: 10,
                  color: 'var(--dash-text-muted)',
                  pointerEvents: 'none',
                }}
              />
              <input
                type="text"
                placeholder="Filter incidents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  padding: '7px 12px 7px 30px',
                  background: 'var(--dash-glass-input-bg)',
                  border: '1px solid var(--dash-glass-border)',
                  borderRadius: 9999,
                  color: 'white',
                  fontSize: '0.82rem',
                }}
              />
            </div>
          </div>
        </div>

        <DataTable
          columns={columns}
          rows={filteredIncidents}
          rowKey={(row) => row.id}
          loading={loading}
          emptyState={
            <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
              <AlertTriangle size={32} style={{ color: 'var(--dash-text-muted)', marginBottom: 8 }} />
              <div style={{ fontWeight: 700, color: '#f8fafc' }}>No incidents match the active filter</div>
              <div style={{ color: 'var(--dash-text-muted)', fontSize: '0.85rem' }}>
                Clear the search query or reset priority filter to view all incidents.
              </div>
            </div>
          }
        />
      </GlassPanel>

      {/* Quick Dispatch Authorization Modal */}
      {dispatchTargetIncident && (
        <ConfirmationModal
          title="Authorize Emergency Rescue Dispatch"
          description={`Incident ID: ${dispatchTargetIncident.id} · Priority: ${dispatchTargetIncident.operational_priority.toUpperCase()}`}
          confirmLabel="Authorize & Dispatch Unit"
          cancelLabel="Cancel"
          loading={dispatching}
          onConfirm={handleAuthorizeDispatch}
          onCancel={() => setDispatchTargetIncident(null)}
        >
          <div style={{ marginTop: 14 }}>
            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, marginBottom: 6, color: '#cbd5e1' }}>
              SELECT AVAILABLE RESCUE UNIT:
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
              TACTICAL INSTRUCTIONS:
            </label>
            <textarea
              rows={3}
              value={dispatchInstructions}
              onChange={(e) => setDispatchInstructions(e.target.value)}
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

            <div
              style={{
                marginTop: 12,
                padding: '8px 12px',
                borderRadius: 6,
                background: 'rgba(255, 51, 102, 0.1)',
                border: '1px solid rgba(255, 51, 102, 0.3)',
                fontSize: '0.75rem',
                color: '#ff8099',
              }}
            >
              🔒 <strong>Human Safety Invariant:</strong> Dispatch will be signed and sealed under Lead Dispatcher ID{' '}
              <code>{raahatService.getDispatcherId().slice(0, 8)}...</code> with immutable audit logging.
            </div>
          </div>
        </ConfirmationModal>
      )}

      {/* Toast Notifications */}
      <ToastNotification toasts={toasts} onDismiss={removeToast} />
    </div>
  );
}
