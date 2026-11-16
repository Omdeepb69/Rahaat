import { Inbox, MapPinOff, PlusCircle, Search, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { LazyMap } from '../../components/LazyMap';
import { Badge, EmptyState, ErrorState, Input, Loading, PriorityBadge, Segmented, StatusBadge, TimeAgo, useToast } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { formatAge, humanize } from '../../lib/format';
import { OPEN_STATUSES, PRIORITY } from '../../lib/labels';
import { useChanges, useNow } from '../../lib/live';
import { useOperation } from '../../lib/operation';
import { useIncidents, useResources } from '../../lib/queries';
import type { IncidentSummary } from '../../lib/types';
import { IncidentPanel } from '../incident/IncidentPanel';
import { RequireOperation } from '../NoOperation';

type View = 'review' | 'open' | 'active';
const VIEW_STATUSES: Record<View, string[]> = {
  review: ['unverified', 'under_review'],
  open: OPEN_STATUSES,
  active: ['verified', 'assigned', 'in_progress'],
};

function QueueItem({ incident, selected, onSelect, now }: { incident: IncidentSummary; selected: boolean; onSelect: () => void; now: number }) {
  return (
    <li>
      <button type="button" className="queue-item" aria-current={selected} onClick={onSelect}>
        <div className="stack-sm" style={{ gap: 4 }}>
          <PriorityBadge priority={incident.priority} source={incident.priority_source} />
        </div>
        <div className="stack-sm" style={{ gap: 2, minWidth: 0 }}>
          <div className="spread">
            <span className="ref" style={{ fontWeight: 700 }}>{incident.reference}</span>
            <span className="xs muted num" title="Time since the incident was opened">{formatAge(incident.created_at, now)}</span>
          </div>
          <span className="small truncate">{incident.summary ?? incident.location.description ?? humanize(incident.category)}</span>
          <span className="row-wrap xs muted">
            <StatusBadge status={incident.status} />
            {incident.people_count != null ? <span className="row"><Users size={11} aria-hidden />{incident.people_count}</span> : <span className="faint">people unknown</span>}
            {incident.trapped && <Badge tone="sev-urgent">Trapped</Badge>}
            {incident.medical_emergency && <Badge tone="sev-urgent">Medical</Badge>}
            {incident.location.status === 'none' && <span className="row" title="No position established"><MapPinOff size={11} aria-hidden />no position</span>}
            {incident.location.status === 'candidate' && <span title="Position not confirmed">position unconfirmed</span>}
            {incident.pending_duplicates > 0 && <Badge tone="tone-warn">possible duplicate</Badge>}
          </span>
        </div>
      </button>
    </li>
  );
}

function Board() {
  const { operation } = useOperation();
  const { can } = useAuth();
  const toast = useToast();
  const now = useNow(15_000);
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<View>('open');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const selected = params.get('incident');

  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const incidents = useIncidents({ disaster_id: operation!.id, status: VIEW_STATUSES[view], q: query || undefined, sort: 'priority', limit: 200 });
  const resources = useResources({ disaster_id: operation!.id, status: ['available', 'assigned'] });
  const items = useMemo(() => incidents.data?.items ?? [], [incidents.data]);

  const { user } = useAuth();
  useChanges((change) => {
    const fresh = Date.now() - Date.parse(change.occurred_at) < 60_000;
    if (change.action === 'incident.created' && change.disaster_id === operation!.id && fresh && change.actor_id !== user?.id) {
      const reference = String(change.payload.reference ?? 'New incident');
      const priority = String(change.payload.priority ?? '');
      const label = priority in PRIORITY ? PRIORITY[priority as keyof typeof PRIORITY].label : '';
      setAnnouncement(`New incident ${reference}${label ? `, ${label}` : ''}`);
      toast('info', `New incident ${reference}${label ? ` · ${label}` : ''}`);
    }
  });

  const select = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set('incident', id); else next.delete('incident');
    setParams(next, { replace: true });
  };

  useEffect(() => {
    document.title = 'Operations board · RAAHAT';
  }, []);

  const selectedIncident = items.find((i) => i.id === selected);
  return (
    <div className="ops">
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
      <section className="ops-queue" aria-label="Incident queue">
        <div className="ops-toolbar">
          <div className="spread">
            <h1 style={{ fontSize: 'var(--text-lg)' }}>Incidents</h1>
            {can('reports:create') && <Link to="/intake" className="btn btn-primary btn-sm"><PlusCircle size={14} aria-hidden />New report</Link>}
          </div>
          <Segmented<View> label="Show" value={view} onChange={setView} options={[
            { value: 'review', label: 'Needs review' }, { value: 'open', label: 'All open' }, { value: 'active', label: 'Verified' },
          ]} />
          <div className="row">
            <Search size={14} aria-hidden className="faint" />
            <label htmlFor="queue-search" className="sr-only">Search incidents</label>
            <Input id="queue-search" type="search" placeholder="Reference, place, words in report" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <span className="xs muted" aria-live="polite">
            {incidents.data ? `${incidents.data.total} incident${incidents.data.total === 1 ? '' : 's'}` : ' '}
            {incidents.dataUpdatedAt > 0 && <> · updated <TimeAgo value={incidents.dataUpdatedAt} /></>}
          </span>
        </div>
        <div className="scroll">
          {incidents.isLoading && <Loading label="Loading incidents" />}
          {incidents.isError && !incidents.data && <ErrorState error={incidents.error} onRetry={() => void incidents.refetch()} />}
          {incidents.data && items.length === 0 && (
            <EmptyState icon={<Inbox size={28} />} title={query ? 'No matches' : view === 'review' ? 'Nothing waiting for review' : 'No open incidents'}>
              {query ? 'Try a different search.' : 'Incidents appear here as reports arrive.'}
            </EmptyState>
          )}
          <ul className="list" aria-label="Incidents by priority">
            {items.map((incident) => (
              <QueueItem key={incident.id} incident={incident} now={now} selected={incident.id === selected} onSelect={() => select(incident.id)} />
            ))}
          </ul>
        </div>
      </section>
      <section className="ops-map" aria-label="Map">
        <LazyMap incidents={items} resources={resources.data?.items ?? []} selectedId={selected} onSelect={select}
          center={selectedIncident?.location.coordinates ?? operation!.map_center} />
      </section>
      <aside className="ops-detail" data-empty={!selected} aria-label="Incident details">
        <div className="scroll">
          {selected ? <IncidentPanel id={selected} onClose={() => select(null)} /> : (
            <EmptyState title="No incident selected">Select an incident in the list or on the map.</EmptyState>
          )}
        </div>
      </aside>
    </div>
  );
}

export function OperationsBoard() {
  return <RequireOperation><Board /></RequireOperation>;
}
