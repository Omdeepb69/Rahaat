import { GitMerge, Link2, Undo2, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge, Button, Dialog, Field, PriorityBadge, StatusBadge, Textarea, useToast } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatDateTime, humanize } from '../../lib/format';
import { mutations } from '../../lib/queries';
import type { DuplicateCandidate, IncidentDetail } from '../../lib/types';
import { SectionHeading } from './SectionHeading';

type Action = 'merge' | 'reject' | 'relate';

const ACTION_TEXT: Record<Action, { title: string; button: string; help: string }> = {
  merge: { title: 'Merge as duplicate', button: 'Merge', help: 'This incident becomes a duplicate of the one you keep. All reports are kept on the surviving incident, and the merge can be reversed.' },
  reject: { title: 'Not a duplicate', button: 'Mark as different', help: 'Both incidents stay separate and this pairing is not suggested again.' },
  relate: { title: 'Related, not the same', button: 'Link as related', help: 'Both incidents stay separate but are shown as part of one situation.' },
};

function ReviewDialog({ incident, candidate, action, onClose }: { incident: IncidentDetail; candidate: DuplicateCandidate; action: Action; onClose: () => void }) {
  const toast = useToast();
  const review = mutations.useReviewDuplicate(incident.id);
  const [reason, setReason] = useState('');
  const [keep, setKeep] = useState(candidate.other.id);
  const submit = async () => {
    try {
      await review.mutateAsync({ linkId: candidate.link_id, action, reason, keep: action === 'merge' ? keep : undefined });
      toast('success', ACTION_TEXT[action].title);
      onClose();
    } catch (error) {
      toast('error', errorMessage(error));
    }
  };
  return (
    <Dialog open title={ACTION_TEXT[action].title} description={ACTION_TEXT[action].help} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={review.isPending} disabled={reason.trim().length < 3} onClick={submit}>{ACTION_TEXT[action].button}</Button></>}>
      {action === 'merge' && (
        <fieldset className="stack-sm" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="label">Which incident continues?</legend>
          {[incident, candidate.other].map((x) => (
            <label key={x.id} className="checkbox">
              <input type="radio" name="keep" checked={keep === x.id} onChange={() => setKeep(x.id)} />
              <span className="ref">{x.reference}</span> <StatusBadge status={x.status} /> <span className="muted small">{x.report_count} report(s)</span>
            </label>
          ))}
        </fieldset>
      )}
      <Field label="Reason" required hint="Recorded in the audit trail.">
        {(p) => <Textarea {...p} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Same phone number and household; caller confirmed on callback" />}
      </Field>
    </Dialog>
  );
}

function CandidateCard({ incident, candidate }: { incident: IncidentDetail; candidate: DuplicateCandidate }) {
  const { can } = useAuth();
  const [action, setAction] = useState<Action | null>(null);
  const pending = candidate.status === 'pending_review';
  return (
    <li className="stack-sm" style={{ padding: '10px 0' }}>
      <div className="spread">
        <div className="row-wrap">
          <Link to={`/control/incidents/${candidate.other.reference}`} className="ref" style={{ fontWeight: 600 }}>{candidate.other.reference}</Link>
          <PriorityBadge priority={candidate.other.priority} />
          <StatusBadge status={candidate.other.status} />
        </div>
        {candidate.score != null && <span className="small muted">match <span className="num">{candidate.score.toFixed(2)}</span></span>}
      </div>
      {candidate.other.summary && <span className="small">{candidate.other.summary}</span>}
      <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
        {candidate.signals.map((s, i) => (
          <li key={i}>
            <strong>{humanize(s.name)}</strong>
            {s.weight > 0 && <span className="muted num"> ({s.score.toFixed(2)} × {s.weight.toFixed(2)})</span>}: {s.detail}
          </li>
        ))}
      </ul>
      {!pending && (
        <span className="small muted">
          {humanize(candidate.status)}{candidate.reviewed_at && ` ${formatDateTime(candidate.reviewed_at)}`}{candidate.review_reason && `: ${candidate.review_reason}`}
        </span>
      )}
      {pending && can('incidents:merge') && incident.status !== 'duplicate' && (
        <div className="row-wrap">
          <Button size="sm" icon={<GitMerge size={13} />} onClick={() => setAction('merge')}>Merge</Button>
          <Button size="sm" icon={<Link2 size={13} />} onClick={() => setAction('relate')}>Related</Button>
          <Button size="sm" icon={<X size={13} />} onClick={() => setAction('reject')}>Different</Button>
        </div>
      )}
      {action && <ReviewDialog incident={incident} candidate={candidate} action={action} onClose={() => setAction(null)} />}
    </li>
  );
}

export function DuplicatesSection({ incident }: { incident: IncidentDetail }) {
  const { can } = useAuth();
  const toast = useToast();
  const unmerge = mutations.useUnmerge(incident.id);
  const [reason, setReason] = useState('');
  const [open, setOpen] = useState(false);
  if (!incident.duplicates.length && incident.status !== 'duplicate') return null;
  const pending = incident.duplicates.filter((d) => d.status === 'pending_review').length;
  return (
    <section className="detail-section" aria-labelledby="dup-h">
      <div className="spread">
        <SectionHeading id="dup-h">Possible duplicates</SectionHeading>
        {pending > 0 && <Badge tone="tone-warn">{pending} to review</Badge>}
      </div>
      {incident.status === 'duplicate' && (
        <div className="callout">
          <div className="stack-sm">
            <span>This incident was merged into another and is not worked on directly.</span>
            {can('incidents:merge') && <Button size="sm" icon={<Undo2 size={13} />} onClick={() => setOpen(true)}>Reverse merge</Button>}
          </div>
        </div>
      )}
      {incident.duplicates.length > 0 && <p className="xs faint">Reports are never merged automatically. Each pairing below was suggested from shared signals and waits for a decision.</p>}
      <ul className="list">{incident.duplicates.map((d) => <CandidateCard key={d.link_id} incident={incident} candidate={d} />)}</ul>
      <Dialog open={open} title="Reverse merge" onClose={() => setOpen(false)}
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" busy={unmerge.isPending} disabled={reason.trim().length < 3}
          onClick={async () => { try { await unmerge.mutateAsync(reason); toast('success', 'Merge reversed'); setOpen(false); } catch (e) { toast('error', errorMessage(e)); } }}>Reverse</Button></>}>
        <Field label="Reason" required>{(p) => <Textarea {...p} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
      </Dialog>
    </section>
  );
}
