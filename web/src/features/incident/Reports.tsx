import { AudioLines, Languages } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge, Button, Callout, TimeAgo, Unknown } from '../../components/ui';
import { buildUrl } from '../../lib/api';
import { formatDateTime, humanize } from '../../lib/format';
import { CHANNEL, LANGUAGES, RECEIVED_VIA } from '../../lib/labels';
import { useReports } from '../../lib/queries';
import { session } from '../../lib/session';
import type { ReportSummary } from '../../lib/types';

function AudioPlayer({ reportId }: { reportId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      const response = await fetch(buildUrl(`/api/v1/reports/${reportId}/audio`), {
        headers: { Authorization: `Bearer ${session.token() ?? ''}` },
      });
      if (!response.ok) throw new Error(response.status === 403 ? 'Your role cannot play recordings.' : 'Recording not available.');
      setUrl(URL.createObjectURL(await response.blob()));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Recording not available.');
    } finally {
      setBusy(false);
    }
  };
  if (url) return <audio controls src={url} style={{ width: '100%' }} />;
  return (
    <div className="row">
      <Button size="sm" icon={<AudioLines size={14} />} busy={busy} onClick={load}>Load recording</Button>
      {error && <span className="small" style={{ color: 'var(--bad)' }}>{error}</span>}
    </div>
  );
}

export function ReportCard({ report, showIncident }: { report: ReportSummary; showIncident?: boolean }) {
  const [showTranslation, setShowTranslation] = useState(true);
  const language = report.original_language ? LANGUAGES[report.original_language] ?? report.original_language : null;
  return (
    <article className="stack-sm" style={{ padding: 'var(--s-3) 0' }}>
      <div className="row-wrap small">
        <Badge>{CHANNEL[report.channel] ?? report.channel}</Badge>
        {report.received_via && report.channel === 'operator' && <span className="muted">{RECEIVED_VIA[report.received_via] ?? humanize(report.received_via)}</span>}
        <time className="num muted" dateTime={report.received_at} title={report.received_at}>{formatDateTime(report.received_at)}</time>
        <span className="faint">(<TimeAgo value={report.received_at} />)</span>
        {language && <Badge tone="tone-outline" title={`Identified by ${report.language_source ?? 'unknown'}`}>{language}</Badge>}
        {showIncident && report.incident_reference && <Link to={`/incidents/${report.incident_reference}`} className="ref">{report.incident_reference}</Link>}
      </div>
      {(report.caller_name || report.caller_contact) && (
        <div className="small"><span className="muted">Caller:</span> {report.caller_name ?? <Unknown>name not given</Unknown>}{report.caller_contact && <span className="num"> · {report.caller_contact}</span>}</div>
      )}
      {report.caller_details_redacted && <div className="small faint">Caller details hidden for your role.</div>}
      {report.original_text ? (
        <div className="stack-sm">
          <div className="transcript" lang={report.original_language ?? undefined}>{report.original_text}</div>
          {report.translated_text && (
            <div className="callout callout-machine">
              <Languages size={16} aria-hidden />
              <div className="stack-sm">
                <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start', padding: 0 }} onClick={() => setShowTranslation((v) => !v)} aria-expanded={showTranslation}>
                  Machine translation ({report.translation_provider ?? 'model'}) {showTranslation ? '— hide' : '— show'}
                </button>
                {showTranslation && <p lang="en">{report.translated_text}</p>}
              </div>
            </div>
          )}
        </div>
      ) : (
        <Unknown>No text: {report.has_audio ? 'audio report not transcribed' : 'empty report'}</Unknown>
      )}
      {report.processing_error && <Callout tone="warn">{report.processing_error}</Callout>}
      {report.processing_status === 'pending' && <span className="small faint">Waiting for the background worker.</span>}
      {report.processing_status === 'pending_enrichment' && <span className="small faint">Translation and model extraction pending.</span>}
      {report.has_audio && <AudioPlayer reportId={report.id} />}
    </article>
  );
}

export function ReportsSection({ incidentId }: { incidentId: string }) {
  const reports = useReports({ disaster_id: null, incident_id: incidentId, limit: 50 });
  return (
    <section className="detail-section" aria-labelledby="reports-h">
      <h3 id="reports-h" className="section-title">Reports ({reports.data?.total ?? '…'})</h3>
      {reports.isError && <Callout tone="bad">Reports could not be loaded.</Callout>}
      <ul className="list">
        {reports.data?.items.map((r) => <li key={r.id}><ReportCard report={r} /></li>)}
      </ul>
    </section>
  );
}
