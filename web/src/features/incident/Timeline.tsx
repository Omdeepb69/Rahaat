import { Loading, Unknown } from '../../components/ui';
import { formatDateTime, humanize } from '../../lib/format';
import { actionLabel, STAGE } from '../../lib/labels';
import { useTimeline } from '../../lib/queries';
import type { TimelineEntry } from '../../lib/types';

function detail(entry: TimelineEntry): string | null {
  const p = entry.payload;
  switch (entry.action) {
    case 'incident.status_changed':
      return `${humanize(String(p.from))} → ${humanize(String(p.to))}${p.closure_reason ? ` (${humanize(String(p.closure_reason))})` : ''}${p.note ? `: ${p.note}` : ''}`;
    case 'incident.triaged':
      return `${humanize(String(p.previous_priority))} → ${humanize(String(p.new_priority))}`;
    case 'incident.corrected': {
      const changes = p.changes as Record<string, { from: unknown; to: unknown }> | undefined;
      return changes ? Object.entries(changes).map(([k, v]) => `${humanize(k)}: ${String(v.from ?? '—')} → ${String(v.to ?? '—')}`).join('; ') + (p.note ? ` (${p.note})` : '') : null;
    }
    case 'dispatch.approved':
      return `${p.callsign}${p.followed_recommendation === false ? `, instead of recommended ${p.recommended_callsign}` : ''}${p.reason ? `: ${p.reason}` : ''}`;
    case 'incident.location_confirmed':
      return String(p.label ?? '') + (p.note ? ` (${p.note})` : '');
    case 'incident.merge_approved':
    case 'incident.unmerged':
    case 'incident.merge_rejected':
      return String(p.reason ?? '');
    case 'dispatch.recommendation_rejected':
      return String(p.reason ?? '');
    default:
      if (entry.action.startsWith('dispatch.')) return `${p.callsign}: ${STAGE[String(p.to)] ?? p.to}${p.note ? ` (${p.note})` : ''}`;
      return null;
  }
}

export function TimelineSection({ incidentId }: { incidentId: string }) {
  const timeline = useTimeline(incidentId);
  return (
    <section className="detail-section" aria-labelledby="tl-h">
      <h3 id="tl-h" className="section-title">Timeline</h3>
      {timeline.isLoading && <Loading />}
      <ol className="timeline">
        {timeline.data?.items.map((e) => (
          <li key={e.seq}>
            <time className="num small muted" dateTime={e.occurred_at} title={e.occurred_at}>{formatDateTime(e.occurred_at)}</time>
            <div className="stack-sm" style={{ gap: 2 }}>
              <span style={{ fontWeight: 600 }}>{actionLabel(e.action)}</span>
              {detail(e) && <span className="small">{detail(e)}</span>}
              <span className="xs muted">{e.actor_name ?? (e.actor_id ? 'Unknown user' : <Unknown>System</Unknown>)}</span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
