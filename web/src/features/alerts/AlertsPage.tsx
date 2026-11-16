import { ExternalLink, Megaphone } from 'lucide-react';
import { useState } from 'react';

import { Badge, Callout, EmptyState, ErrorState, Loading, PageHeader, Pager, Panel, TimeAgo, Unknown } from '../../components/ui';
import { formatDateTime, formatFull } from '../../lib/format';
import { useNow } from '../../lib/live';
import { useAlerts } from '../../lib/queries';
import type { OfficialAlert } from '../../lib/types';

const LIMIT = 50;
const SEVERITY_TONE: Record<string, string> = {
  Extreme: 'sev-critical_review', Severe: 'sev-urgent', Moderate: 'sev-unassessed', Minor: 'sev-standard',
};

function AlertRow({ alert, now }: { alert: OfficialAlert; now: number }) {
  const expired = alert.expires_at ? Date.parse(alert.expires_at) < now : false;
  const details = alert.details as { sender?: string; event?: string; urgency?: string; certainty?: string; instruction?: string; headlines?: Record<string, string> };
  const local = Object.entries(details.headlines ?? {}).filter(([lang]) => !lang.startsWith('en'));
  return (
    <li className="stack-sm" style={{ padding: 'var(--s-3) var(--s-4)', opacity: expired ? 0.6 : 1 }}>
      <div className="row-wrap">
        {alert.severity ? <Badge tone={SEVERITY_TONE[alert.severity] ?? 'tone-outline'}>{alert.severity}</Badge> : <Badge>Severity not stated</Badge>}
        {details.event && <strong>{details.event}</strong>}
        {expired ? <Badge tone="tone-idle">Expired</Badge> : <Badge tone="tone-ok">Active</Badge>}
        {alert.authority === 'official' ? <Badge tone="tone-outline">Official · NDMA SACHET</Badge> : <Badge tone="tone-warn">Source not verified as official</Badge>}
      </div>
      <p>{alert.headline}</p>
      {local.map(([lang, text]) => <p key={lang} className="script small muted" lang={lang}>{text}</p>)}
      <dl className="kv small">
        <dt>Issued by</dt><dd>{details.sender ?? <Unknown>Not stated</Unknown>}</dd>
        <dt>Area</dt><dd>{alert.area_description ?? <Unknown>Not stated</Unknown>}</dd>
        <dt>Issued</dt><dd>{alert.issued_at ? <time dateTime={alert.issued_at} title={formatFull(alert.issued_at)}>{formatDateTime(alert.issued_at)}</time> : <Unknown>Not stated</Unknown>}</dd>
        <dt>Expires</dt><dd>{alert.expires_at ? <time dateTime={alert.expires_at} title={formatFull(alert.expires_at)}>{formatDateTime(alert.expires_at)}</time> : <Unknown>No expiry given</Unknown>}</dd>
        {(details.urgency || details.certainty) && <><dt>Urgency / certainty</dt><dd>{details.urgency ?? '—'} / {details.certainty ?? '—'}</dd></>}
        {details.instruction && <><dt>Instruction</dt><dd>{details.instruction}</dd></>}
        <dt>Fetched by RAAHAT</dt><dd><TimeAgo value={alert.fetched_at} /></dd>
      </dl>
      {alert.source_url && <a className="small row" href={alert.source_url} target="_blank" rel="noreferrer noopener">Original CAP message <ExternalLink size={12} aria-hidden /></a>}
    </li>
  );
}

export function AlertsPage() {
  const [showExpired, setShowExpired] = useState(false);
  const [offset, setOffset] = useState(0);
  const alerts = useAlerts({ active_only: !showExpired, limit: LIMIT, offset });
  const now = useNow(60_000);
  const data = alerts.data;
  return (
    <div className="page">
      <PageHeader title="Official alerts" description="Warnings published by issuing authorities through the configured CAP feed. Shown for reference; they do not create incidents." />
      {alerts.isLoading && <Loading />}
      {alerts.isError && <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />}
      {data && !data.configured && (
        <Callout title="No alert feed is configured">
          Set CAP_ALERT_FEED_URL on the server to import warnings, for example the NDMA SACHET feed for Kerala or Goa. Until then this page stays empty; no alerts are shown from any other source.
        </Callout>
      )}
      {data?.configured && (
        <Panel flush title={
          <div className="row-wrap">
            <label className="checkbox small"><input type="checkbox" checked={showExpired} onChange={(e) => { setShowExpired(e.target.checked); setOffset(0); }} />Include expired</label>
            <span className="xs muted">{data.last_fetched_at ? <>Feed last read <TimeAgo value={data.last_fetched_at} /> · checked every 5 min</> : 'Feed not read yet'}</span>
          </div>
        } footer={<Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}>
          {data.items.length === 0 ? (
            <EmptyState icon={<Megaphone size={28} />} title={showExpired ? 'No alerts received yet' : 'No active alerts'}>
              {showExpired ? 'The feed has not published any alerts since it was configured.' : 'Nothing currently in force from the configured feed. Include expired alerts to see earlier ones.'}
            </EmptyState>
          ) : (
            <ul className="list">{data.items.map((a) => <AlertRow key={a.id} alert={a} now={now} />)}</ul>
          )}
        </Panel>
      )}
    </div>
  );
}
