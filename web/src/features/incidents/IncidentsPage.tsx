import { ArrowDownUp, Inbox } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { Badge, EmptyState, ErrorState, Input, SkeletonList, PageHeader, Pager, Panel, PriorityBadge, Select, StatusBadge, TimeAgo, Unknown } from '../../components/ui';
import { formatDateTime, humanize } from '../../lib/format';
import { CATEGORIES, INCIDENT_STATUS, LOCATION_SOURCE, PRIORITY, PRIORITY_ORDER } from '../../lib/labels';
import { useOperation } from '../../lib/operation';
import { useIncidentCounts, useIncidents } from '../../lib/queries';
import type { IncidentStatus } from '../../lib/types';
import { RequireOperation } from '../NoOperation';

const LIMIT = 50;

function Counts() {
  const { operation } = useOperation();
  const counts = useIncidentCounts(operation!.id);
  if (!counts.data) return null;
  const c = counts.data;
  const open = Object.values(c.open_by_priority).reduce((a, b) => a + (b ?? 0), 0);
  return (
    <div className="panel metrics" aria-label="Open incidents">
      <div className="metric"><span className="small muted">Open incidents</span><span className="metric-value">{open}</span></div>
      {PRIORITY_ORDER.map((p) => (
        <div key={p} className="metric"><span className="small muted">{PRIORITY[p].label}</span><span className="metric-value">{c.open_by_priority[p] ?? 0}</span></div>
      ))}
      <div className="metric"><span className="small muted">No position</span><span className="metric-value">{c.open_without_location}</span></div>
    </div>
  );
}

function List() {
  const { operation } = useOperation();
  const [params, setParams] = useSearchParams();
  const status = params.get('status') ?? 'open';
  const priority = params.get('priority') ?? '';
  const category = params.get('category') ?? '';
  const sort = params.get('sort') ?? 'priority';
  const offset = Number(params.get('offset') ?? 0);
  const [search, setSearch] = useState(params.get('q') ?? '');

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'offset') next.delete('offset');
    setParams(next, { replace: true });
  };
  useEffect(() => {
    const t = setTimeout(() => { if ((params.get('q') ?? '') !== search.trim()) update('q', search.trim()); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const incidents = useIncidents({
    disaster_id: operation!.id,
    status: status === 'all' ? undefined : [status],
    priority: priority ? [priority] : undefined,
    category: category ? [category] : undefined,
    q: params.get('q') ?? undefined,
    sort, limit: LIMIT, offset,
  });

  return (
    <div className="page page-wide">
      <PageHeader title="Incidents" description={`${operation!.name}. Every incident and its current state.`} />
      <Counts />
      <Panel flush title={
        <div className="row-wrap" role="search">
          <label className="sr-only" htmlFor="inc-q">Search</label>
          <Input id="inc-q" type="search" placeholder="Search reference, place or report text" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 280 }} />
          <label className="sr-only" htmlFor="inc-status">Status</label>
          <Select id="inc-status" value={status} onChange={(e) => update('status', e.target.value)} style={{ width: 'auto' }}>
            <option value="open">All open</option>
            {(Object.keys(INCIDENT_STATUS) as IncidentStatus[]).map((s) => <option key={s} value={s}>{INCIDENT_STATUS[s].label}</option>)}
            <option value="all">Any status</option>
          </Select>
          <label className="sr-only" htmlFor="inc-priority">Priority</label>
          <Select id="inc-priority" value={priority} onChange={(e) => update('priority', e.target.value)} style={{ width: 'auto' }}>
            <option value="">Any priority</option>
            {PRIORITY_ORDER.map((p) => <option key={p} value={p}>{PRIORITY[p].label}</option>)}
          </Select>
          <label className="sr-only" htmlFor="inc-category">Category</label>
          <Select id="inc-category" value={category} onChange={(e) => update('category', e.target.value)} style={{ width: 'auto' }}>
            <option value="">Any category</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
          </Select>
          <label className="sr-only" htmlFor="inc-sort">Sort</label>
          <span className="row"><ArrowDownUp size={14} aria-hidden className="faint" />
            <Select id="inc-sort" value={sort} onChange={(e) => update('sort', e.target.value)} style={{ width: 'auto' }}>
              <option value="priority">Priority, then oldest</option><option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option><option value="updated">Recently updated</option><option value="reference">Reference</option>
            </Select>
          </span>
        </div>
      } footer={incidents.data && <Pager total={incidents.data.total} limit={LIMIT} offset={offset} onChange={(o) => update('offset', String(o))} />}>
        {incidents.isLoading && <SkeletonList rows={6} />}
        {incidents.isError && <ErrorState error={incidents.error} onRetry={() => void incidents.refetch()} />}
        {incidents.data && incidents.data.items.length === 0 && <EmptyState icon={<Inbox size={22} />} title="No incidents match">Change the filters or search.</EmptyState>}
        {incidents.data && incidents.data.items.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Incidents</caption>
              <thead><tr><th>Reference</th><th>Priority</th><th>Status</th><th>Situation</th><th>People</th><th>Location</th><th>Opened</th><th>Updated</th></tr></thead>
              <tbody>
                {incidents.data.items.map((i) => (
                  <tr key={i.id}>
                    <td><Link className="row-link ref" to={`/incidents/${i.reference}`}>{i.reference}</Link></td>
                    <td><PriorityBadge priority={i.priority} source={i.priority_source} /></td>
                    <td><div className="stack-sm" style={{ gap: 2 }}><StatusBadge status={i.status} />{i.pending_duplicates > 0 && <Badge tone="tone-warn">possible duplicate</Badge>}</div></td>
                    <td style={{ maxWidth: 360 }}><div>{i.summary ?? humanize(i.category)}</div>{(i.trapped || i.medical_emergency) && <div className="xs" style={{ color: 'var(--sev-urgent)' }}>{[i.trapped && 'trapped', i.medical_emergency && 'medical need'].filter(Boolean).join(', ')}</div>}</td>
                    <td className="num">{i.people_count ?? <Unknown>?</Unknown>}</td>
                    <td style={{ maxWidth: 240 }}>
                      {i.location.status === 'none' ? <Unknown>Not established</Unknown> : (
                        <div className="stack-sm" style={{ gap: 0 }}>
                          <span className="truncate">{i.location.label ?? i.location.description}</span>
                          <span className="xs muted">{i.location.status === 'confirmed' ? 'Confirmed' : 'Unconfirmed'} · {i.location.source && LOCATION_SOURCE[i.location.source]}</span>
                        </div>
                      )}
                    </td>
                    <td className="num small" title={i.created_at}>{formatDateTime(i.created_at)}</td>
                    <td className="small"><TimeAgo value={i.updated_at} /></td>
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

export function IncidentsPage() {
  return <RequireOperation><List /></RequireOperation>;
}
