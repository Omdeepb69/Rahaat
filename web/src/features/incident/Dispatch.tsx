import { AlertTriangle, ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';
import { useState } from 'react';

import { Badge, Button, Callout, Dialog, Field, Loading, Select, Textarea, useToast } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatDateTime, formatDistance, formatDuration, humanize } from '../../lib/format';
import { STAGE } from '../../lib/labels';
import { mutations, useAssignments, useRecommendation } from '../../lib/queries';
import type { Assignment, Candidate, IncidentDetail } from '../../lib/types';
import { SectionHeading } from './SectionHeading';

function distanceText(c: Candidate): string {
  if (c.distance_m == null) return 'distance unknown';
  if (c.distance_basis === 'road_route') return `${formatDistance(c.distance_m)} by road${c.travel_seconds ? `, ~${formatDuration(c.travel_seconds * 1000)}` : ''}`;
  return `${formatDistance(c.distance_m)} straight line`;
}

function CandidateRow({ candidate, top, canDecide, onChoose }: { candidate: Candidate; top: boolean; canDecide: boolean; onChoose: () => void }) {
  const [open, setOpen] = useState(top);
  return (
    <li className="candidate-card" data-top={top}>
      <div className="spread">
        <button type="button" className="btn btn-ghost btn-sm" style={{ padding: 0, height: 'auto' }} onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span className="num" style={{ fontWeight: 700 }}>#{candidate.rank}</span>
          <span style={{ fontWeight: 600 }}>{candidate.callsign}</span>
          <span className="muted small">{humanize(candidate.resource_type)}</span>
        </button>
        <div className="row">
          <span className="num small" title="Recommendation score out of 100">{candidate.score.toFixed(0)}</span>
          {canDecide && <Button size="sm" variant={top ? 'primary' : 'default'} onClick={onChoose}>{top ? 'Approve' : 'Choose'}</Button>}
        </div>
      </div>
      <span className="small muted">{distanceText(candidate)}{candidate.covered.length > 0 && ` · provides ${candidate.covered.map(humanize).join(', ')}`}</span>
      {candidate.warnings.map((w) => <span key={w} className="small row" style={{ color: 'var(--warn)' }}><AlertTriangle size={12} aria-hidden /> {w}</span>)}
      {open && (
        <table className="table small" style={{ marginTop: 4, background: 'var(--surface)', borderRadius: 'var(--radius-xs)' }}>
          <caption className="sr-only">Score breakdown for {candidate.callsign}</caption>
          <thead><tr><th>Factor</th><th>Weight</th><th style={{ width: '30%' }}>Value</th><th>Points</th></tr></thead>
          <tbody>
            {candidate.factors.map((f) => (
              <tr key={f.name}>
                <td><div>{humanize(f.name)}</div><div className="xs muted">{f.detail}</div></td>
                <td className="num">{f.weight.toFixed(2)}</td>
                <td><div className="score-bar" aria-hidden><span style={{ width: `${f.value * 100}%` }} /></div><span className="xs num">{f.value.toFixed(2)}</span></td>
                <td className="num">{f.contribution.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </li>
  );
}

function ApproveDialog({ incident, candidate, recommended, onClose }: { incident: IncidentDetail; candidate: Candidate; recommended: Candidate | null; onClose: () => void }) {
  const toast = useToast();
  const approve = mutations.useApprove(incident.id);
  const override = recommended != null && recommended.resource_id !== candidate.resource_id;
  const [reason, setReason] = useState('');
  const submit = async () => {
    try {
      await approve.mutateAsync({ resource_id: candidate.resource_id, reason: reason.trim() || undefined });
      toast('success', `${candidate.callsign} committed to ${incident.reference}`);
      onClose();
    } catch (error) {
      toast('error', errorMessage(error));
    }
  };
  return (
    <Dialog open title={`Commit ${candidate.callsign} to ${incident.reference}?`} onClose={onClose}
      description="This records your decision and marks the resource as committed. It does not contact the team: inform them through your normal channel."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" icon={<ShieldCheck size={14} />} busy={approve.isPending} disabled={override && !reason.trim()} onClick={submit}>Approve dispatch</Button></>}>
      <dl className="kv">
        <dt>Resource</dt><dd>{candidate.callsign} · {candidate.name}</dd>
        <dt>Distance</dt><dd>{distanceText(candidate)}</dd>
        <dt>Score</dt><dd className="num">{candidate.score.toFixed(1)} / 100</dd>
      </dl>
      {candidate.warnings.length > 0 && <Callout tone="warn">{candidate.warnings.join('. ')}</Callout>}
      {override && <Callout tone="warn" title="Different from the recommendation">The system ranked {recommended!.callsign} first. Give the reason for choosing {candidate.callsign}.</Callout>}
      <Field label={override ? 'Reason' : 'Note (optional)'} required={override}>
        {(p) => <Textarea {...p} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={override ? 'e.g. BOAT-2 knows the area; BOAT-1 crew is resting' : ''} />}
      </Field>
    </Dialog>
  );
}

function DeclineDialog({ incident, onClose }: { incident: IncidentDetail; onClose: () => void }) {
  const toast = useToast();
  const decline = mutations.useDecline(incident.id);
  const [reason, setReason] = useState('');
  return (
    <Dialog open title="Do not dispatch now" onClose={onClose}
      description="Records that a person reviewed the recommendation and decided against committing a resource for now."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={decline.isPending} disabled={reason.trim().length < 3}
        onClick={async () => { try { await decline.mutateAsync(reason); toast('success', 'Decision recorded'); onClose(); } catch (e) { toast('error', errorMessage(e)); } }}>Record decision</Button></>}>
      <Field label="Reason" required>{(p) => <Textarea {...p} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Waiting for callback to confirm address" />}</Field>
    </Dialog>
  );
}

export function ProgressControl({ assignment }: { assignment: Assignment }) {
  const { can } = useAuth();
  const toast = useToast();
  const progress = mutations.useProgress();
  const [stage, setStage] = useState('');
  const [note, setNote] = useState('');
  if (assignment.status !== 'approved' || !can('dispatch:progress')) return null;
  const options = assignment.next_stages.filter((s) => s !== 'cancelled' || can('dispatch:decide'));
  const needsNote = stage === 'cancelled';
  return (
    <form className="row-wrap" onSubmit={async (e) => {
      e.preventDefault();
      if (!stage) return;
      try {
        await progress.mutateAsync({ assignmentId: assignment.id, stage, note: note || undefined });
        toast('success', `${assignment.callsign}: ${STAGE[stage] ?? stage}`);
        setStage(''); setNote('');
      } catch (error) {
        toast('error', errorMessage(error));
      }
    }}>
      <label className="sr-only" htmlFor={`stage-${assignment.id}`}>Next stage for {assignment.callsign}</label>
      <Select id={`stage-${assignment.id}`} value={stage} onChange={(e) => setStage(e.target.value)} style={{ width: 'auto' }}>
        <option value="">Update progress…</option>
        {options.map((s) => <option key={s} value={s}>{STAGE[s] ?? s}</option>)}
      </Select>
      {stage && (
        <>
          <label className="sr-only" htmlFor={`note-${assignment.id}`}>Note</label>
          <input id={`note-${assignment.id}`} className="input" style={{ width: 200 }} placeholder={needsNote ? 'Reason (required)' : 'Note (optional)'} value={note} onChange={(e) => setNote(e.target.value)} />
          <Button type="submit" size="sm" variant="primary" busy={progress.isPending} disabled={needsNote && !note.trim()}>Record</Button>
        </>
      )}
    </form>
  );
}

function AssignmentList({ incidentId }: { incidentId: string }) {
  const assignments = useAssignments({ incident_id: incidentId });
  const items = assignments.data?.items ?? [];
  if (!items.length) return null;
  return (
    <div className="stack-sm">
      <span className="small muted">Assignments</span>
      <ul className="list">
        {items.map((a) => (
          <li key={a.id} className="stack-sm" style={{ padding: '8px 0' }}>
            <div className="spread">
              <span><strong>{a.callsign}</strong> <span className="muted small">{a.resource_name}</span></span>
              <Badge tone={a.status === 'approved' ? 'tone-accent' : 'tone-idle'}>{STAGE[a.stage] ?? a.stage}</Badge>
            </div>
            <span className="xs muted">
              Approved {a.approved_at && formatDateTime(a.approved_at)}
              {a.followed_recommendation === false && ' · chose a different resource than recommended'}
              {a.decision_reason && ` · “${a.decision_reason}”`}
            </span>
            <ProgressControl assignment={a} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DispatchSection({ incident }: { incident: IncidentDetail }) {
  const { can } = useAuth();
  const open = ['verified', 'assigned', 'in_progress', 'unverified', 'under_review'].includes(incident.status);
  const recommendation = useRecommendation(incident.id, can('dispatch:read') && open);
  const [choice, setChoice] = useState<Candidate | null>(null);
  const [declining, setDeclining] = useState(false);
  if (!can('dispatch:read')) return null;
  const rec = recommendation.data;
  const canDecide = can('dispatch:decide') && !!rec?.can_dispatch;
  const committed = incident.active_assignments > 0;
  return (
    <section className="detail-section" aria-labelledby="dispatch-h">
      <div className="spread">
        <SectionHeading id="dispatch-h">Dispatch</SectionHeading>
        {rec && <span className="small muted" title={rec.priority_score.terms.map((t) => `${t.detail}: ${t.points}`).join('\n')}>Priority score <span className="num">{rec.priority_score.total.toFixed(0)}</span></span>}
      </div>
      <AssignmentList incidentId={incident.id} />
      {!open && <span className="small muted">This incident is {incident.status.replace('_', ' ')}; no recommendation is computed.</span>}
      {open && recommendation.isLoading && <Loading label="Ranking resources" />}
      {open && recommendation.isError && <Callout tone="bad">{errorMessage(recommendation.error)}</Callout>}
      {rec && open && (
        <div className="stack-sm">
          {rec.blocked_reason && <Callout tone="warn">{rec.blocked_reason}</Callout>}
          {committed && rec.candidates.length > 0 && <span className="small muted">Additional resources that could also be sent:</span>}
          {rec.requirements.length > 0 && (
            <div className="small"><span className="muted">Needs: </span>{rec.requirements.map((r) => <span key={r.capability} title={r.reason}><Badge>{humanize(r.capability)}</Badge> </span>)}</div>
          )}
          {rec.candidates.length === 0 ? (
            <Callout tone={committed ? 'info' : 'warn'} title={committed ? 'No additional suitable resource is available' : 'No suitable resource is available'}>
              {rec.excluded.length ? `${rec.excluded.length} resource(s) considered and excluded.` : 'No resources are registered for this operation.'}
            </Callout>
          ) : (
            <ol aria-label="Recommended resources" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {rec.candidates.slice(0, 5).map((c, i) => (
                <CandidateRow key={c.resource_id} candidate={c} top={i === 0} canDecide={canDecide} onChoose={() => setChoice(c)} />
              ))}
            </ol>
          )}
          {rec.excluded.length > 0 && (
            <details className="small">
              <summary className="muted">Excluded ({rec.excluded.length})</summary>
              <ul style={{ margin: 0, paddingLeft: 18 }}>{rec.excluded.map((e) => <li key={e.resource_id}>{e.callsign}: {e.reason}</li>)}</ul>
            </details>
          )}
          <details className="small">
            <summary className="muted">What this recommendation does not know ({rec.limitations.length})</summary>
            <ul style={{ margin: 0, paddingLeft: 18 }}>{rec.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
            <p className="xs faint" style={{ marginTop: 4 }}>Method: {rec.objective}. Engine {rec.engine_version}.</p>
          </details>
          {canDecide && <Button size="sm" variant="ghost" onClick={() => setDeclining(true)}>Do not dispatch now…</Button>}
        </div>
      )}
      {choice && rec && <ApproveDialog incident={incident} candidate={choice} recommended={rec.candidates[0] ?? null} onClose={() => setChoice(null)} />}
      {declining && <DeclineDialog incident={incident} onClose={() => setDeclining(false)} />}
    </section>
  );
}
