import { ShieldCheck, ShieldX } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge, Button, Callout, EmptyState, ErrorState, Loading, PageHeader, Pager, Panel, Select, Unknown } from '../../components/ui';
import { formatDateTime, formatFull, humanize } from '../../lib/format';
import { actionLabel } from '../../lib/labels';
import { useOperation } from '../../lib/operation';
import { useAudit, useChainCheck } from '../../lib/queries';

const LIMIT = 100;
const FILTERS: Record<string, string> = {
  '': 'Everything', 'incident.': 'Incidents', 'dispatch.': 'Dispatch', 'resource.': 'Resources', 'report.': 'Reports', 'user.': 'Accounts', 'operation.': 'Operations',
};

function summary(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const key of ['reference', 'incident_reference', 'callsign', 'from', 'to', 'reason', 'note', 'username', 'role']) {
    const value = payload[key];
    if (value !== undefined && value !== null && value !== '') parts.push(`${humanize(key)}: ${String(value)}`);
  }
  return parts.join(' · ');
}

export function ActivityPage() {
  const { operation } = useOperation();
  const [prefix, setPrefix] = useState('');
  const [scope, setScope] = useState<'operation' | 'all'>('operation');
  const [offset, setOffset] = useState(0);
  const [verify, setVerify] = useState(false);
  const audit = useAudit({ disaster_id: scope === 'operation' ? operation?.id : undefined, action_prefix: prefix || undefined, limit: LIMIT, offset });
  const check = useChainCheck(verify);
  return (
    <div className="page page-wide">
      <PageHeader title="Activity log" description="Every change, who made it and when. Each record is hash-chained to the previous one for the same item."
        actions={<Button icon={<ShieldCheck size={14} />} busy={check.isFetching} onClick={() => (verify ? void check.refetch() : setVerify(true))}>Verify integrity</Button>} />
      {check.data && (check.data.verified ? (
        <Callout title="Audit trail intact"><ShieldCheck size={14} aria-hidden /> Recomputed {check.data.events_checked} records across {check.data.entities_checked} items. No record has been altered or removed. Checked {formatFull(check.data.checked_at)}.</Callout>
      ) : (
        <Callout tone="bad" title="Audit trail integrity failure">
          <ShieldX size={14} aria-hidden /> {check.data.broken.length} chain(s) do not match their stored content. Records may have been altered outside the application.
          <ul>{check.data.broken.slice(0, 10).map((b) => <li key={b.entity_id} className="num xs">{b.entity_type} {b.entity_id}: {b.failure}</li>)}</ul>
        </Callout>
      ))}
      {check.isError && <ErrorState error={check.error} />}
      <Panel flush title={
        <div className="row-wrap">
          <label className="sr-only" htmlFor="act-f">Type</label>
          <Select id="act-f" value={prefix} onChange={(e) => { setPrefix(e.target.value); setOffset(0); }} style={{ width: 'auto' }}>{Object.entries(FILTERS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
          <label className="sr-only" htmlFor="act-s">Scope</label>
          <Select id="act-s" value={scope} onChange={(e) => { setScope(e.target.value as 'operation' | 'all'); setOffset(0); }} style={{ width: 'auto' }}>
            <option value="operation">This operation</option><option value="all">All operations and accounts</option>
          </Select>
        </div>
      } footer={audit.data && <Pager total={audit.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}>
        {audit.isLoading && <Loading />}
        {audit.isError && <ErrorState error={audit.error} onRetry={() => void audit.refetch()} />}
        {audit.data?.items.length === 0 && <EmptyState title="No activity yet" />}
        {!!audit.data?.items.length && (
          <div className="table-wrap">
            <table className="table small">
              <thead><tr><th>#</th><th>Time</th><th>Action</th><th>By</th><th>Item</th><th>Details</th></tr></thead>
              <tbody>
                {audit.data.items.map((e) => (
                  <tr key={e.id}>
                    <td className="num faint">{e.seq}</td>
                    <td className="num" title={formatFull(e.occurred_at)}>{formatDateTime(e.occurred_at)}</td>
                    <td>{actionLabel(e.action)}</td>
                    <td>{e.actor_name ?? (e.actor_id ? <Unknown>Unknown user</Unknown> : <Badge>System</Badge>)}</td>
                    <td>{e.incident_id ? <Link className="num" to={`/incidents/${e.incident_id}`}>{String(e.payload.incident_reference ?? e.payload.reference ?? 'Incident')}</Link> : humanize(e.entity_type)}</td>
                    <td style={{ maxWidth: 420 }}>{summary(e.payload)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
