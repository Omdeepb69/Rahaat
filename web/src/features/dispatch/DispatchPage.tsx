import { Inbox, ListChecks } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge, Button, Callout, EmptyState, ErrorState, Loading, PageHeader, Panel, PriorityBadge, TimeAgo } from '../../components/ui';
import { formatDistance, formatDuration, humanize } from '../../lib/format';
import { STAGE } from '../../lib/labels';
import { useNow } from '../../lib/live';
import { useOperation } from '../../lib/operation';
import { useAssignments, useDispatchQueue, usePlan } from '../../lib/queries';
import { ProgressControl } from '../incident/Dispatch';
import { RequireOperation } from '../NoOperation';

function Queue() {
  const { operation } = useOperation();
  const queue = useDispatchQueue(operation!.id);
  const now = useNow(30_000);
  return (
    <Panel flush title="Awaiting a resource" id="q-h" actions={queue.dataUpdatedAt > 0 && <span className="xs muted">updated <TimeAgo value={queue.dataUpdatedAt} /></span>}>
      {queue.isLoading && <Loading />}
      {queue.isError && <ErrorState error={queue.error} onRetry={() => void queue.refetch()} />}
      {queue.data?.length === 0 && <EmptyState icon={<Inbox size={28} />} title="No verified incident is waiting">Incidents appear here once a person has verified them and until a resource is committed.</EmptyState>}
      {!!queue.data?.length && (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Verified incidents ordered by priority score</caption>
            <thead><tr><th>#</th><th>Incident</th><th>Priority</th><th>Score</th><th>Waiting</th><th>Position</th></tr></thead>
            <tbody>
              {queue.data.map((q, i) => (
                <tr key={q.incident_id}>
                  <td className="num">{i + 1}</td>
                  <td><Link className="row-link ref" to={`/?incident=${q.incident_id}`}>{q.reference}</Link><div className="xs muted">{humanize(q.category)}</div></td>
                  <td><PriorityBadge priority={q.priority} /></td>
                  <td>
                    <details>
                      <summary className="num" style={{ cursor: 'pointer' }}>{q.priority_score.total.toFixed(0)}</summary>
                      <ul className="xs" style={{ margin: 0, paddingLeft: 16 }}>{q.priority_score.terms.map((t) => <li key={t.name}><span className="num">+{t.points}</span> {t.detail}</li>)}</ul>
                    </details>
                  </td>
                  <td className="num small">{formatDuration(now - Date.parse(q.created_at))}</td>
                  <td>{q.has_position ? <span className="small">Recorded</span> : <Badge tone="tone-warn">None</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="panel-footer xs faint">
        Score = triage level + 20 per person (max 20) + conditions (trapped, medical, vulnerable, rising water) + 2 per minute waiting (max 3 h). It orders the work; it does not replace the triage level.
      </div>
    </Panel>
  );
}

function PlanView() {
  const { operation } = useOperation();
  const [requested, setRequested] = useState(false);
  const plan = usePlan(operation!.id, requested);
  return (
    <Panel title="Proposed pairing" id="plan-h" actions={<Button size="sm" icon={<ListChecks size={14} />} busy={plan.isFetching} onClick={() => (requested ? void plan.refetch() : setRequested(true))}>{requested ? 'Recompute' : 'Compute'}</Button>}>
      {!requested && <p className="small muted">Pairs every waiting incident with an available resource, highest priority first. Nothing is committed; each pairing still needs approval on the incident.</p>}
      {plan.isError && <ErrorState error={plan.error} />}
      {plan.data && (
        <div className="stack-sm">
          <p className="xs faint">{plan.data.method} Computed <TimeAgo value={plan.data.generated_at} />.</p>
          {plan.data.entries.length === 0 && <span className="small muted">Nothing is waiting.</span>}
          <ul className="list">
            {plan.data.entries.map((e) => (
              <li key={e.incident_id} className="spread" style={{ padding: '8px 0' }}>
                <span><Link className="ref" to={`/?incident=${e.incident_id}`}>{e.incident_reference}</Link> <span className="xs muted num">score {e.priority_score.toFixed(0)}</span></span>
                {e.candidate ? (
                  <span className="small"><strong>{e.candidate.callsign}</strong> · {e.candidate.distance_m != null ? formatDistance(e.candidate.distance_m) : 'distance unknown'}{e.candidate.warnings.length > 0 && <Badge tone="tone-warn">{e.candidate.warnings.length} warning</Badge>}</span>
                ) : <span className="small" style={{ color: 'var(--warn)' }}>{e.reason_unassigned}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function Active() {
  const { operation } = useOperation();
  const assignments = useAssignments({ disaster_id: operation!.id, active_only: true });
  return (
    <Panel flush title="Active assignments" id="act-h">
      {assignments.isLoading && <Loading />}
      {assignments.isError && <ErrorState error={assignments.error} />}
      {assignments.data?.items.length === 0 && <EmptyState title="No resources are committed">Approved assignments appear here until they are completed or cancelled.</EmptyState>}
      {!!assignments.data?.items.length && (
        <ul className="list">
          {assignments.data.items.map((a) => (
            <li key={a.id} className="stack-sm" style={{ padding: 'var(--s-3) var(--s-4)' }}>
              <div className="spread">
                <span><strong>{a.callsign}</strong> → <Link className="ref" to={`/?incident=${a.incident_id}`}>{a.incident_reference}</Link> <PriorityBadge priority={a.incident_priority} /></span>
                <Badge tone="tone-accent">{STAGE[a.stage] ?? a.stage}</Badge>
              </div>
              <span className="xs muted">{a.incident_location_label ?? 'Position not established'} · updated <TimeAgo value={a.updated_at} /></span>
              <ProgressControl assignment={a} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Page() {
  return (
    <div className="page page-wide">
      <PageHeader title="Dispatch" description="Recommendations are computed from recorded facts and positions. A person approves every commitment." />
      <Callout>RAAHAT records dispatch decisions. It does not contact teams or emergency services: communicate each decision through your normal channel.</Callout>
      <div className="grid-2">
        <Queue />
        <div className="stack-lg"><Active /><PlanView /></div>
      </div>
    </div>
  );
}

export function DispatchPage() {
  return <RequireOperation><Page /></RequireOperation>;
}
