import { useState, useEffect, useMemo, useCallback } from 'react';
import { Shield, Navigation, CheckCircle2, Search } from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { GlassPanel } from '../components/GlassPanel';
import { MetricCard } from '../components/MetricCard';
import { StatusBadge } from '../components/StatusBadge';
import { DataTable, type Column } from '../components/DataTable';
import { SecondaryButton } from '../components/SecondaryButton';
import { PrimaryButton } from '../components/PrimaryButton';
import { ConfirmationModal } from '../components/ConfirmationModal';
import { ToastNotification } from '../components/ToastNotification';
import { raahatService } from '../services/raahatService';
import type { Resource, Incident } from '../types/raahat';
import type { ToastMessage } from '../types/dashboard';
import { useAuth } from '../context/AuthContext';
import {
  calculateDistanceKm,
  DEOC_COVERAGE_RADIUS_KM,
  SEOC_COVERAGE_RADIUS_KM,
} from '../utils/geoUtils';

export function OperationsPage() {
  const { session } = useAuth();
  const [resources, setResources] = useState<Resource[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Dispatch modal
  const [targetResource, setTargetResource] = useState<Resource | null>(null);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string>('');
  const [instructions, setInstructions] = useState<string>('Rapid evacuation deployment');
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
    try {
      const radiusMeters = session?.district_code
        ? DEOC_COVERAGE_RADIUS_KM * 1000
        : SEOC_COVERAGE_RADIUS_KM * 1000;
      const [resList, incList] = await Promise.all([
        raahatService.getResources(
          session?.center_lat != null && session?.center_lng != null
            ? { lat: session.center_lat, lon: session.center_lng, radius_meters: radiusMeters }
            : undefined
        ),
        raahatService.getIncidents({ priority: 'critical_review' }),
      ]);
      setResources(resList);
      setIncidents(incList);
    } catch (err) {
      console.error('Failed to load fleet data', err);
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const filteredResources = useMemo(() => {
    const centerLat = session?.center_lat;
    const centerLng = session?.center_lng;
    const maxRadius = session?.district_code
      ? DEOC_COVERAGE_RADIUS_KM
      : SEOC_COVERAGE_RADIUS_KM;

    return resources.filter((r) => {
      // Jurisdiction geospatial bounding filter
      if (centerLat != null && centerLng != null) {
        if (!r.location?.latitude || !r.location?.longitude) return false;
        const dist = calculateDistanceKm(
          centerLat,
          centerLng,
          r.location.latitude,
          r.location.longitude
        );
        if (dist > maxRadius) return false;
      }

      if (typeFilter !== 'all' && (r.resource_type || '').toLowerCase() !== typeFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          r.name.toLowerCase().includes(q) ||
          r.resource_type.toLowerCase().includes(q) ||
          r.availability_status.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [resources, typeFilter, searchQuery, session]);

  const handleDispatch = async () => {
    if (!targetResource || !selectedIncidentId) return;

    setDispatching(true);
    try {
      await raahatService.dispatchResource({
        disaster_id: targetResource.disaster_id,
        incident_id: selectedIncidentId,
        resource_id: targetResource.id,
        instructions,
      });

      addToast(
        'success',
        'Resource Dispatched',
        `${targetResource.name} deployed to Incident ${selectedIncidentId.slice(0, 8)}...`
      );
      setTargetResource(null);
      setSelectedIncidentId('');
      await loadData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Dispatch failed';
      addToast('error', 'Dispatch Error', message);
    } finally {
      setDispatching(false);
    }
  };

  const columns: Column<Resource>[] = [
    {
      key: 'name',
      header: 'Unit Name',
      render: (row) => (
        <div>
          <div style={{ fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Shield size={14} style={{ color: '#10b981' }} />
            <span>{row.name}</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--dash-text-muted)', fontFamily: 'monospace' }}>
            ID: {row.id.slice(0, 8)}...
          </div>
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Asset Type',
      render: (row) => (
        <span style={{ textTransform: 'uppercase', fontWeight: 700, fontSize: '0.8rem', color: '#38bdf8' }}>
          {row.resource_type}
        </span>
      ),
    },
    {
      key: 'capacity',
      header: 'Capacity',
      render: (row) => (
        <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>
          {row.capacity} persons
        </span>
      ),
    },
    {
      key: 'location',
      header: 'Base Coordinates',
      render: (row) => (
        <span style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--dash-text-muted)' }}>
          {row.location?.latitude?.toFixed(4)}, {row.location?.longitude?.toFixed(4)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.availability_status} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      render: (row) => {
        const isAvailable = (row.availability_status || '').toLowerCase() === 'available';
        return (
          <PrimaryButton
            disabled={!isAvailable}
            style={{
              minHeight: 30,
              padding: '0.25rem 0.8rem',
              fontSize: '0.75rem',
              opacity: isAvailable ? 1 : 0.4,
            }}
            onClick={() => {
              setTargetResource(row);
              if (incidents.length > 0) setSelectedIncidentId(incidents[0].id);
            }}
          >
            Assign Mission
          </PrimaryButton>
        );
      },
    },
  ];

  const availableCount = filteredResources.filter((r) => (r.availability_status || '').toLowerCase() === 'available').length;
  const assignedCount = filteredResources.filter((r) => (r.availability_status || '').toLowerCase() === 'assigned').length;

  return (
    <div style={{ padding: '1.25rem 1.5rem', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title="Rescue Operations & Fleet Registry"
        subtitle="Live tracking and human-authorized mission assignments for emergency rescue units"
        actions={
          <SecondaryButton onClick={loadData}>
            <span>↻ Refresh Fleet</span>
          </SecondaryButton>
        }
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <MetricCard
          label="TOTAL FLEET ASSETS"
          value={filteredResources.length}
          deltaLabel={session?.district_name ? `Active in ${session.district_name}` : 'Active in Sector'}
          icon={<Shield size={20} style={{ color: '#38bdf8' }} />}
        />
        <MetricCard
          label="AVAILABLE FOR MISSION"
          value={availableCount}
          deltaLabel="Standby Ready"
          icon={<CheckCircle2 size={20} style={{ color: '#10b981' }} />}
          onClick={() => setTypeFilter('all')}
        />
        <MetricCard
          label="ASSIGNED / IN TRANSIT"
          value={assignedCount}
          deltaLabel="Currently on Rescue Mission"
          icon={<Navigation size={20} style={{ color: '#f59e0b' }} />}
        />
      </div>

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
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f8fafc' }}>Fleet Assets</h2>
            <div style={{ fontSize: '0.82rem', color: 'var(--dash-text-muted)' }}>
              Showing {filteredResources.length} units
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
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
              {['all', 'boat', 'ambulance', 'drone', 'rescue_team'].map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setTypeFilter(type)}
                  style={{
                    border: 'none',
                    background: typeFilter === type ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                    color: typeFilter === type ? '#38bdf8' : 'var(--dash-text-muted)',
                    fontWeight: 700,
                    fontSize: '0.78rem',
                    padding: '4px 12px',
                    borderRadius: 9999,
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {type.replace('_', ' ')}
                </button>
              ))}
            </div>

            <div style={{ position: 'relative' }}>
              <Search
                size={14}
                style={{ position: 'absolute', left: 10, top: 10, color: 'var(--dash-text-muted)' }}
              />
              <input
                type="text"
                placeholder="Search unit name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
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
          rows={filteredResources}
          rowKey={(row) => row.id}
          loading={loading}
        />
      </GlassPanel>

      {/* Mission Assignment Modal */}
      {targetResource && (
        <ConfirmationModal
          title={`Assign Mission: ${targetResource.name}`}
          description={`Asset: ${targetResource.name} (${targetResource.resource_type.toUpperCase()} · Cap: ${targetResource.capacity})`}
          confirmLabel="Authorize Mission"
          cancelLabel="Cancel"
          loading={dispatching}
          onConfirm={handleDispatch}
          onCancel={() => setTargetResource(null)}
        >
          <div style={{ marginTop: 14 }}>
            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, marginBottom: 6, color: '#cbd5e1' }}>
              TARGET INCIDENT:
            </label>
            <select
              value={selectedIncidentId}
              onChange={(e) => setSelectedIncidentId(e.target.value)}
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
              <option value="">-- Choose Incident --</option>
              {incidents.map((inc) => (
                <option key={inc.id} value={inc.id}>
                  [{inc.operational_priority.toUpperCase()}] Incident {inc.id.slice(0, 8)}... (
                  {inc.severity_facts?.people_count || 1} people)
                </option>
              ))}
            </select>

            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, marginBottom: 6, color: '#cbd5e1' }}>
              OPERATIONAL ORDERS:
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
