import { useState, useEffect, useMemo, useCallback } from 'react';
import { Radio, PhoneCall, Globe, MessageSquare, Search, Volume2 } from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { GlassPanel } from '../components/GlassPanel';
import { MetricCard } from '../components/MetricCard';
import { DataTable, type Column } from '../components/DataTable';
import { SecondaryButton } from '../components/SecondaryButton';
import { raahatService } from '../services/raahatService';
import type { Report } from '../types/raahat';
import { useAuth } from '../context/AuthContext';
import {
  filterReportsByJurisdiction,
  DEOC_COVERAGE_RADIUS_KM,
  SEOC_COVERAGE_RADIUS_KM,
} from '../utils/geoUtils';

export function ReportsFeedPage() {
  const { session } = useAuth();
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [channelFilter, setChannelFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const loadReports = useCallback(async () => {
    try {
      const data = await raahatService.getReports(100);
      setReports(data);
    } catch (err) {
      console.error('Failed to load distress reports', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReports();

    const unsubscribe = raahatService.connectEventStream((evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.type === 'report.received') {
          loadReports();
        }
      } catch {
        loadReports();
      }
    });

    return () => {
      unsubscribe();
    };
  }, [loadReports]);

  const scopedReports = useMemo(() => {
    const radius = session?.district_code
      ? DEOC_COVERAGE_RADIUS_KM
      : SEOC_COVERAGE_RADIUS_KM;
    return filterReportsByJurisdiction(
      reports,
      session?.state_code,
      session?.district_name,
      session?.center_lat,
      session?.center_lng,
      radius
    );
  }, [reports, session]);

  const filteredReports = useMemo(() => {
    return scopedReports.filter((rep) => {
      if (channelFilter !== 'all' && (rep.source_type || '').toLowerCase() !== channelFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const text = (rep.raw_payload?.text || rep.raw_payload?.situation_description || '').toLowerCase();
        const loc = (rep.raw_payload?.location_text || '').toLowerCase();
        const id = rep.id.toLowerCase();
        const phone = (rep.source_identity || rep.raw_payload?.caller_phone || '').toLowerCase();
        return text.includes(q) || loc.includes(q) || id.includes(q) || phone.includes(q);
      }
      return true;
    });
  }, [scopedReports, channelFilter, searchQuery]);

  const columns: Column<Report>[] = [
    {
      key: 'channel',
      header: 'Channel',
      width: '130px',
      render: (row) => {
        const src = (row.source_type || '').toLowerCase();
        let icon = <Globe size={13} />;
        let color = '#38bdf8';
        let bg = 'rgba(56, 189, 248, 0.15)';

        if (src === 'ivr') {
          icon = <PhoneCall size={13} />;
          color = '#a855f7';
          bg = 'rgba(168, 85, 247, 0.15)';
        } else if (src === 'sms') {
          icon = <MessageSquare size={13} />;
          color = '#f59e0b';
          bg = 'rgba(245, 158, 11, 0.15)';
        } else if (src === 'radio') {
          icon = <Radio size={13} />;
          color = '#10b981';
          bg = 'rgba(16, 185, 129, 0.15)';
        }

        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 9px',
              borderRadius: 9999,
              background: bg,
              color,
              border: `1px solid ${color}40`,
              fontSize: '0.75rem',
              fontWeight: 800,
              textTransform: 'uppercase',
            }}
          >
            {icon}
            <span>{src}</span>
          </span>
        );
      },
    },
    {
      key: 'transcript',
      header: 'Distress Content & Audio Transcript',
      render: (row) => {
        const payload = row.raw_payload || {};
        const text = payload.text || payload.situation_description || 'Distress signal received.';
        const transcripts = payload.transcripts || [];

        return (
          <div>
            <div style={{ color: '#f8fafc', fontSize: '0.88rem', lineHeight: 1.4, fontWeight: 500 }}>
              {text}
            </div>
            {transcripts.length > 0 && (
              <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', color: '#38bdf8' }}>
                <Volume2 size={13} />
                <span>
                  ASR ({transcripts[0].language?.toUpperCase() || 'HI'}): &ldquo;{transcripts[0].text}&rdquo; (
                  {Math.round((transcripts[0].confidence || 0.95) * 100)}% conf)
                </span>
              </div>
            )}
          </div>
        );
      },
    },
    {
      key: 'location',
      header: 'Reported Location',
      width: '180px',
      render: (row) => {
        const loc = row.raw_payload?.location_text || 'GPS Coordinates Provided';
        return (
          <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.85rem' }}>
            📍 {loc}
          </div>
        );
      },
    },
    {
      key: 'people',
      header: 'Headcount',
      width: '100px',
      render: (row) => {
        const count = row.raw_payload?.people_count || 1;
        return (
          <span style={{ fontFamily: 'monospace', fontWeight: 800, color: '#cbd5e1' }}>
            {count} {count === 1 ? 'person' : 'people'}
          </span>
        );
      },
    },
    {
      key: 'time',
      header: 'Received At',
      width: '150px',
      render: (row) => {
        const d = new Date(row.created_at);
        return (
          <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', color: 'var(--dash-text-muted)' }}>
            {d.toLocaleTimeString()} · {d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
          </span>
        );
      },
    },
  ];

  const ivrCount = scopedReports.filter((r) => (r.source_type || '').toLowerCase() === 'ivr').length;
  const webCount = scopedReports.filter((r) => (r.source_type || '').toLowerCase() === 'web').length;
  const smsCount = scopedReports.filter((r) => (r.source_type || '').toLowerCase() === 'sms').length;

  return (
    <div style={{ padding: '1.25rem 1.5rem', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title="Multichannel Distress Ingestion Stream"
        subtitle={session?.district_name ? `Sector intake pipeline for ${session.district_name}` : "Unified intake pipeline aggregating AI helpline calls, Web SOS, SMS, and radio messages"}
        actions={
          <SecondaryButton onClick={loadReports}>
            <span>↻ Refresh Reports</span>
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
          label="TOTAL INGESTED SIGNALS"
          value={scopedReports.length}
          deltaLabel={session?.district_name ? `Active in ${session.district_name}` : "Across all channels"}
          icon={<Radio size={20} style={{ color: '#38bdf8' }} />}
          onClick={() => setChannelFilter('all')}
        />
        <MetricCard
          label="AI VOICE CALLS (IVR)"
          value={ivrCount}
          deltaLabel="Gnani Prisma v3.0 STT"
          icon={<PhoneCall size={20} style={{ color: '#a855f7' }} />}
          onClick={() => setChannelFilter('ivr')}
        />
        <MetricCard
          label="CITIZEN WEB SOS"
          value={webCount}
          deltaLabel="GPS Verified Forms"
          icon={<Globe size={20} style={{ color: '#10b981' }} />}
          onClick={() => setChannelFilter('web')}
        />
        <MetricCard
          label="SMS & RADIO GATEWAY"
          value={smsCount}
          deltaLabel="Cellular & Off-grid"
          icon={<MessageSquare size={20} style={{ color: '#f59e0b' }} />}
          onClick={() => setChannelFilter('sms')}
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
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f8fafc' }}>Distress Signal Feed</h2>
            <div style={{ fontSize: '0.82rem', color: 'var(--dash-text-muted)' }}>
              Showing {filteredReports.length} signals
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
              {['all', 'ivr', 'web', 'sms', 'radio'].map((ch) => (
                <button
                  key={ch}
                  type="button"
                  onClick={() => setChannelFilter(ch)}
                  style={{
                    border: 'none',
                    background: channelFilter === ch ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                    color: channelFilter === ch ? '#38bdf8' : 'var(--dash-text-muted)',
                    fontWeight: 700,
                    fontSize: '0.78rem',
                    padding: '4px 12px',
                    borderRadius: 9999,
                    cursor: 'pointer',
                    textTransform: 'uppercase',
                  }}
                >
                  {ch}
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
                placeholder="Search reports..."
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
          rows={filteredReports}
          rowKey={(row) => row.id}
          loading={loading}
        />
      </GlassPanel>
    </div>
  );
}

