import { RefreshCw } from 'lucide-react';
import { Fragment } from 'react';

import { Button, Callout, ErrorState, HealthBadge, Loading, PageHeader, Panel, TimeAgo, useToast } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatDuration, humanize } from '../../lib/format';
import { useConnection, useStream } from '../../lib/live';
import { mutations, useSystemStatus } from '../../lib/queries';
import type { Component } from '../../lib/types';

function bytes(value: unknown): string {
  if (typeof value !== 'number') return '—';
  const gb = value / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(value / 1e6).toFixed(0)} MB`;
}

function Metrics({ component }: { component: Component }) {
  const m = component.metrics;
  const rows: [string, string][] = [];
  if (component.key === 'database') rows.push(['Schema', String(m.schema_revision ?? '—')], ['Size', bytes(m.size_bytes)], ['Connections', String(m.connections ?? '—')]);
  if (component.key === 'worker') {
    rows.push(['Reports waiting', String(m.reports_waiting ?? '—')]);
    if (typeof m.oldest_waiting_seconds === 'number') rows.push(['Oldest waiting', formatDuration(m.oldest_waiting_seconds * 1000)]);
    if (typeof m.processed_total === 'number') rows.push(['Processed since start', String(m.processed_total)]);
    if (typeof m.failed_total === 'number') rows.push(['Failed since start', String(m.failed_total)]);
  }
  if (component.key === 'realtime') rows.push(['Connected clients', String(m.subscribers ?? 0)]);
  if (component.key === 'host') rows.push(['Disk free', bytes(m.disk_free_bytes)], ['Memory available', bytes(m.memory_available_bytes)], ['Load (1 min)', `${m.load_1m ?? '—'} on ${m.cpu_count ?? '?'} cores`]);
  if (typeof m.last_error === 'string' && m.last_error) rows.push(['Last error', m.last_error]);
  if (!rows.length) return null;
  return <dl className="kv small">{rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd className="num">{v}</dd></Fragment>)}</dl>;
}

function ComponentRow({ component }: { component: Component }) {
  const { can } = useAuth();
  const toast = useToast();
  const probe = mutations.useProbe();
  return (
    <li className="stack-sm" style={{ padding: 'var(--s-3) var(--s-4)' }}>
      <div className="spread">
        <strong>{component.name}</strong>
        <HealthBadge status={component.status} />
      </div>
      <span className="small">{component.detail}</span>
      <span className="xs muted">
        {component.checked_at ? <>Checked <TimeAgo value={component.checked_at} /></> : 'Never checked'}
        {component.last_success_at && <> · last success <TimeAgo value={component.last_success_at} /></>}
        {component.latency_ms != null && <> · {component.latency_ms.toFixed(0)} ms</>}
      </span>
      <Metrics component={component} />
      {component.can_probe && can('system:manage') && (
        <Button size="sm" style={{ alignSelf: 'flex-start' }} busy={probe.isPending} onClick={async () => {
          try { const r = await probe.mutateAsync(component.key); toast(r.status === 'operational' ? 'success' : 'error', `${component.name}: ${humanize(r.status)}`); } catch (e) { toast('error', errorMessage(e)); }
        }}>Run live check</Button>
      )}
    </li>
  );
}

export function SystemPage() {
  const status = useSystemStatus();
  const connection = useConnection();
  const stream = useStream();
  const groups: [string, Component['group']][] = [['Core services', 'core'], ['Host', 'host'], ['Providers and data sources', 'provider']];
  return (
    <div className="page">
      <PageHeader title="System status" description="Every status here is the result of a real check. Providers show the outcome of their last real use or live check."
        actions={<Button icon={<RefreshCw size={14} />} busy={status.isFetching} onClick={() => void status.refetch()}>Check now</Button>} />
      <Panel title="This browser">
        <dl className="kv">
          <dt>Server</dt><dd>{connection.backend === 'online' ? 'Reachable' : connection.backend === 'offline' ? 'Unreachable' : humanize(connection.backend)}{connection.lastContactAt && <> · last contact <TimeAgo value={connection.lastContactAt} /></>}</dd>
          <dt>Live updates</dt><dd>{humanize(stream.state)}{stream.lastMessageAt && <> · last message <TimeAgo value={stream.lastMessageAt} /></>}{stream.lastSeq != null && <span className="faint num"> · seq {stream.lastSeq}</span>}</dd>
        </dl>
      </Panel>
      {status.isLoading && <Loading label="Checking components" />}
      {status.isError && <ErrorState title="Status could not be retrieved" error={status.error} onRetry={() => void status.refetch()} />}
      {status.data && (
        <>
          <div className="row-wrap">
            <span>Overall</span><HealthBadge status={status.data.overall} />
            <span className="small muted">Version {status.data.version} · {status.data.environment} · generated <TimeAgo value={status.data.generated_at} /></span>
          </div>
          {status.data.notices.map((n) => <Callout key={n} tone="warn">{n}</Callout>)}
          {groups.map(([title, group]) => (
            <Panel key={group} flush title={title}>
              <ul className="list">{status.data.components.filter((c) => c.group === group).map((c) => <ComponentRow key={c.key} component={c} />)}</ul>
            </Panel>
          ))}
        </>
      )}
    </div>
  );
}
