import { Inbox, MapPinOff, PlusCircle, Users } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { LazyMap } from '../../components/LazyMap';
import { Badge, EmptyState, ErrorState, PriorityBadge, SearchInput, Segmented, SkeletonList, StatusBadge, TimeAgo, useToast } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { formatAge, humanize } from '../../lib/format';
import { OPEN_STATUSES, PRIORITY, PRIORITY_ORDER } from '../../lib/labels';
import { useChanges, useNow } from '../../lib/live';
import { useOperation } from '../../lib/operation';
import { useIncidentCounts, useIncidents, useResources } from '../../lib/queries';
import type { IncidentSummary, Priority } from '../../lib/types';
import { IncidentPanel } from '../incident/IncidentPanel';
import { RequireOperation } from '../NoOperation';

type View = 'review' | 'open' | 'active';
const VIEW_STATUSES: Record<View, string[]> = {
  review: ['unverified', 'under_review'],
  open: OPEN_STATUSES,
  active: ['verified', 'assigned', 'in_progress'],
};

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
}

function Situation({ priority, onPriority }: { priority: Priority | null; onPriority: (p: Priority | null) => void }) {
  const { operation } = useOperation();
  const counts = useIncidentCounts(operation!.id);
  const c = counts.data;
  const open = c ? Object.values(c.open_by_priority).reduce((a, b) => a + (b ?? 0), 0) : null;
  const review = c ? (c.by_status.unverified ?? 0) + (c.by_status.under_review ?? 0) : null;
  const value = (v: number | null | undefined) => (v == null ? '–' : v);
  return (
    <div className="situation" role="group" aria-label="Open incidents by priority. Select to filter the queue.">
      <button type="button" className="situation-item" aria-pressed={priority === null} onClick={() => onPriority(null)}>
        <span className="situation-value">{value(open)}</span>
        <span className="situation-label">Open incidents</span>
      </button>
      <span className="situation-sep" aria-hidden />
      {PRIORITY_ORDER.filter((p) => p !== 'low').map((p) => (
        <button key={p} type="button" className="situation-item" aria-pressed={priority === p} onClick={() => onPriority(priority === p ? null : p)}>
          <span className="situation-value" style={{ color: c?.open_by_priority[p] ? `var(--sev-${p === 'critical_review' ? 'critical' : p})` : undefined }}>
            {value(c?.open_by_priority[p] ?? (c ? 0 : null))}
          </span>
          <span className="situation-label">{PRIORITY[p].label}</span>
        </button>
      ))}
      <span className="situation-sep" aria-hidden />
      <div className="situation-item" style={{ cursor: 'default' }}>
        <span className="situation-value">{value(review)}</span>
        <span className="situation-label">Awaiting review</span>
      </div>
      <div className="situation-item" style={{ cursor: 'default' }}>
        <span className="situation-value">{value(c?.open_without_location)}</span>
        <span className="situation-label">No position</span>
      </div>
    </div>
  );
}

function QueueItem({ incident, selected, onSelect, now }: { incident: IncidentSummary; selected: boolean; onSelect: () => void; now: number }) {
  return (
    <li>
      <button type="button" className="queue-item" data-priority={incident.priority} aria-current={selected} onClick={onSelect} data-incident={incident.id}>
        <span className="queue-title">
          <span className="ref">{incident.reference}</span>
          <PriorityBadge priority={incident.priority} source={incident.priority_source} />
        </span>
        <span className="queue-age" title="Time since the incident was opened">{formatAge(incident.created_at, now)}</span>
        <span className="queue-summary script">{incident.summary ?? incident.location.description ?? humanize(incident.category)}</span>
        <span className="queue-meta">
          <StatusBadge status={incident.status} />
          {incident.people_count != null
            ? <span className="meta"><Users size={12} aria-hidden />{incident.people_count} {incident.people_count === 1 ? 'person' : 'people'}</span>
            : <span className="meta faint">people unknown</span>}
          {incident.trapped && <Badge tone="sev-urgent">Trapped</Badge>}
          {incident.medical_emergency && <Badge tone="sev-urgent">Medical</Badge>}
          {incident.location.status === 'none' && <span className="meta"><MapPinOff size={12} aria-hidden />No position</span>}
          {incident.location.status === 'candidate' && <span className="meta">Position unconfirmed</span>}
          {incident.pending_duplicates > 0 && <Badge tone="tone-warn">Possible duplicate</Badge>}
        </span>
      </button>
    </li>
  );
}

function Board() {
  const { operation } = useOperation();
  const { can, user } = useAuth();
  const toast = useToast();
  const now = useNow(15_000);
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<View>('open');
  const [priority, setPriority] = useState<Priority | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const selected = params.get('incident');

  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    document.title = 'Operations board · RAAHAT';
  }, []);

  const incidents = useIncidents({
    disaster_id: operation!.id, status: VIEW_STATUSES[view], priority: priority ? [priority] : undefined,
    q: query || undefined, sort: 'priority', limit: 200,
  });
  const resources = useResources({ disaster_id: operation!.id, status: ['available', 'assigned'] });
  const items = useMemo(() => incidents.data?.items ?? [], [incidents.data]);

  useChanges((change) => {
    const fresh = Date.now() - Date.parse(change.occurred_at) < 60_000;
    if (change.action === 'incident.created' && change.disaster_id === operation!.id && fresh && change.actor_id !== user?.id) {
      const reference = String(change.payload.reference ?? 'New incident');
      const p = String(change.payload.priority ?? '');
      const label = p in PRIORITY ? PRIORITY[p as Priority].label : '';
      setAnnouncement(`New incident ${reference}${label ? `, ${label}` : ''}`);
      toast('info', `New incident ${reference}${label ? `, ${label}` : ''}`);
    }
  });

  const select = useCallback((id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set('incident', id); else next.delete('incident');
    setParams(next, { replace: true });
  }, [params, setParams]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      if (document.querySelector('dialog[open]')) return;
      if (event.key === '/' && !isTyping(event.target)) {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (isTyping(event.target)) {
        if (event.key === 'Escape' && event.target === searchRef.current) searchRef.current?.blur();
        return;
      }
      const index = items.findIndex((i) => i.id === selected);
      if (event.key === 'j' || event.key === 'ArrowDown') {
        const next = items[Math.min(items.length - 1, index + 1)];
        if (next) { event.preventDefault(); select(next.id); }
      } else if (event.key === 'k' || event.key === 'ArrowUp') {
        const prev = items[Math.max(0, index - 1)];
        if (prev && index !== -1) { event.preventDefault(); select(prev.id); }
      } else if (event.key === 'Escape' && selected) {
        select(null);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [items, selected, select]);

  useEffect(() => {
    if (!selected) return;
    listRef.current?.querySelector<HTMLElement>(`[data-incident="${selected}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  const selectedIncident = items.find((i) => i.id === selected);
  const filtered = !!query || !!priority;
  return (
    <div className="ops-frame">
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
      <Situation priority={priority} onPriority={setPriority} />
      <div className="ops">
        <section className="ops-queue" aria-labelledby="queue-h">
          <div className="ops-toolbar">
            <div className="spread">
              <h1 id="queue-h" style={{ fontSize: 'var(--text-lg)' }}>Incident queue</h1>
              {can('reports:create') && <Link to="/intake" className="btn btn-primary btn-sm"><PlusCircle size={14} aria-hidden />New report</Link>}
            </div>
            <Segmented<View> label="Show" value={view} onChange={setView} options={[
              { value: 'review', label: 'Needs review' }, { value: 'open', label: 'All open' }, { value: 'active', label: 'Verified' },
            ]} />
            <label htmlFor="queue-search" className="sr-only">Search incidents</label>
            <SearchInput id="queue-search" ref={searchRef} shortcut="/" placeholder="Reference, place or words in a report" value={search} onChange={(e) => setSearch(e.target.value)} />
            <div className="spread xs muted" aria-live="polite">
              <span>
                {incidents.data ? `${incidents.data.total} ${incidents.data.total === 1 ? 'incident' : 'incidents'}${priority ? `, ${PRIORITY[priority].label.toLowerCase()}` : ''}` : ' '}
              </span>
              {incidents.dataUpdatedAt > 0 && <span>Updated <TimeAgo value={incidents.dataUpdatedAt} /></span>}
            </div>
          </div>
          <div className="scroll">
            {incidents.isLoading && <SkeletonList rows={7} label="Loading incidents" />}
            {incidents.isError && !incidents.data && <ErrorState error={incidents.error} onRetry={() => void incidents.refetch()} />}
            {incidents.data && items.length === 0 && (
              <EmptyState icon={<Inbox size={22} />} title={filtered ? 'No incidents match' : view === 'review' ? 'Nothing waiting for review' : 'No open incidents'}
                action={filtered ? <button type="button" className="btn btn-sm" onClick={() => { setSearch(''); setPriority(null); }}>Clear filters</button> : undefined}>
                {filtered ? 'Try a different search or priority.' : 'Incidents appear here as reports arrive.'}
              </EmptyState>
            )}
            <ul className="list" ref={listRef} aria-label="Incidents, highest priority first">
              {items.map((incident) => (
                <QueueItem key={incident.id} incident={incident} now={now} selected={incident.id === selected} onSelect={() => select(incident.id)} />
              ))}
            </ul>
          </div>
          {items.length > 0 && (
            <div className="ops-hint" style={{ padding: 'var(--s-2) var(--s-4)', boxShadow: 'inset 0 1px 0 var(--line)' }} aria-hidden>
              <span><kbd className="kbd">j</kbd><kbd className="kbd">k</kbd> move</span>
              <span><kbd className="kbd">/</kbd> search</span>
              <span><kbd className="kbd">Esc</kbd> close</span>
            </div>
          )}
        </section>
        <section className="ops-map" aria-label="Map">
          <LazyMap incidents={items} resources={resources.data?.items ?? []} selectedId={selected} onSelect={select}
            center={selectedIncident?.location.coordinates ?? operation!.map_center} />
        </section>
        <aside className="ops-detail" data-empty={!selected} aria-label="Incident details">
          <div className="scroll">
            {selected ? <IncidentPanel id={selected} onClose={() => select(null)} /> : (
              <EmptyState title="No incident selected">Choose an incident in the queue or on the map. Use j and k to move through the queue.</EmptyState>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

export function OperationsBoard() {
  return <RequireOperation><Board /></RequireOperation>;
}
