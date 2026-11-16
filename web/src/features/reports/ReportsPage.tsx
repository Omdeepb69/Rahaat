import { Inbox } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge, Button, Dialog, EmptyState, ErrorState, Input, SkeletonList, PageHeader, Pager, Panel, Select, TimeAgo, Unknown } from '../../components/ui';
import { formatDateTime, formatFull, humanize } from '../../lib/format';
import { CHANNEL, LANGUAGES } from '../../lib/labels';
import { useOperation } from '../../lib/operation';
import { useReport, useReports } from '../../lib/queries';
import { ReportCard } from '../incident/Reports';
import { RequireOperation } from '../NoOperation';

const LIMIT = 50;
const PROCESSING: Record<string, { label: string; tone: string }> = {
  pending: { label: 'Waiting', tone: 'tone-warn' },
  claimed: { label: 'Processing', tone: 'tone-accent' },
  pending_enrichment: { label: 'Translation pending', tone: 'tone-outline' },
  processed: { label: 'Processed', tone: 'tone-ok' },
  failed: { label: 'Failed', tone: 'tone-bad' },
};

function ReportDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const report = useReport(id);
  return (
    <Dialog open wide title="Report" onClose={onClose} footer={<Button onClick={onClose}>Close</Button>}>
      {report.isLoading && <SkeletonList rows={6} />}
      {report.isError && <ErrorState error={report.error} />}
      {report.data && (
        <>
          <ReportCard report={report.data} showIncident />
          <div className="stack-sm">
            <h3 className="section-title">Processing history</h3>
            <div className="table-wrap">
              <table className="table small">
                <thead><tr><th>Stage</th><th>Provider</th><th>Outcome</th><th>Time</th><th>Details</th></tr></thead>
                <tbody>
                  {report.data.processing_runs.map((r, i) => (
                    <tr key={i}>
                      <td>{humanize(r.stage)}</td>
                      <td>{r.provider}{r.model && <div className="xs muted">{r.model}</div>}</td>
                      <td><Badge tone={r.status === 'succeeded' ? 'tone-ok' : r.status === 'failed' ? 'tone-bad' : 'tone-idle'}>{humanize(r.status)}</Badge></td>
                      <td className="num" title={formatFull(r.created_at)}>{r.duration_ms != null ? `${r.duration_ms.toFixed(0)} ms` : '—'}</td>
                      <td className="xs" style={{ maxWidth: 320 }}>{r.error ?? Object.entries(r.details).filter(([, v]) => v !== null && typeof v !== 'object').map(([k, v]) => `${humanize(k)}: ${String(v)}`).join(' · ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </Dialog>
  );
}

function List() {
  const { operation } = useOperation();
  const [channel, setChannel] = useState('');
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const reports = useReports({ disaster_id: operation!.id, channel: channel ? [channel] : undefined, processing_status: status ? [status] : undefined, q: q || undefined, limit: LIMIT, offset });
  return (
    <div className="page page-wide">
      <PageHeader title="Reports" description="Every report received, as received. Original text is never altered." />
      <Panel flush title={
        <div className="row-wrap" role="search">
          <label className="sr-only" htmlFor="rep-q">Search text</label>
          <Input id="rep-q" type="search" placeholder="Search report text" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} style={{ width: 260 }} />
          <label className="sr-only" htmlFor="rep-ch">Channel</label>
          <Select id="rep-ch" value={channel} onChange={(e) => { setChannel(e.target.value); setOffset(0); }} style={{ width: 'auto' }}>
            <option value="">Any channel</option>{Object.entries(CHANNEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <label className="sr-only" htmlFor="rep-st">Processing</label>
          <Select id="rep-st" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} style={{ width: 'auto' }}>
            <option value="">Any processing state</option>{Object.entries(PROCESSING).map(([v, l]) => <option key={v} value={v}>{l.label}</option>)}
          </Select>
        </div>
      } footer={reports.data && <Pager total={reports.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}>
        {reports.isLoading && <SkeletonList rows={6} />}
        {reports.isError && <ErrorState error={reports.error} onRetry={() => void reports.refetch()} />}
        {reports.data?.items.length === 0 && <EmptyState icon={<Inbox size={22} />} title="No reports">Reports appear here as they are entered or received.</EmptyState>}
        {!!reports.data?.items.length && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Received</th><th>Channel</th><th>Report</th><th>Language</th><th>Incident</th><th>Processing</th></tr></thead>
              <tbody>
                {reports.data.items.map((r) => (
                  <tr key={r.id}>
                    <td className="num small"><div>{formatDateTime(r.received_at)}</div><div className="faint"><TimeAgo value={r.received_at} /></div></td>
                    <td className="small">{CHANNEL[r.channel] ?? r.channel}</td>
                    <td style={{ maxWidth: 480 }}>
                      <button type="button" className="btn btn-ghost" style={{ height: 'auto', padding: 0, textAlign: 'left', whiteSpace: 'normal', fontWeight: 400 }} onClick={() => setOpen(r.id)}>
                        <span className="script">{r.original_text ? (r.original_text.length > 160 ? `${r.original_text.slice(0, 160)}…` : r.original_text) : <Unknown>{r.has_audio ? 'Audio, not transcribed' : 'No text'}</Unknown>}</span>
                      </button>
                    </td>
                    <td className="small">{r.original_language ? LANGUAGES[r.original_language] ?? r.original_language : <Unknown>—</Unknown>}{r.translated_text && <div className="xs" style={{ color: 'var(--machine)' }}>translated</div>}</td>
                    <td>{r.incident_reference ? <Link className="ref" to={`/incidents/${r.incident_reference}`}>{r.incident_reference}</Link> : <Unknown>none yet</Unknown>}</td>
                    <td><Badge tone={PROCESSING[r.processing_status]?.tone}>{PROCESSING[r.processing_status]?.label ?? r.processing_status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {open && <ReportDialog id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

export function ReportsPage() {
  return <RequireOperation><List /></RequireOperation>;
}
