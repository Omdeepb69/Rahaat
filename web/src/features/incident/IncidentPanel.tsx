import { ExternalLink, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Button, Callout, Dialog, ErrorState, Field, Loading, PriorityBadge, Select, StatusBadge, Textarea, TimeAgo, useToast } from '../../components/ui';
import { ApiError, errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { humanize } from '../../lib/format';
import { INCIDENT_STATUS } from '../../lib/labels';
import { mutations, useIncident } from '../../lib/queries';
import type { IncidentDetail, IncidentStatus } from '../../lib/types';
import { DispatchSection } from './Dispatch';
import { DuplicatesSection } from './Duplicates';
import { FactsSection } from './Facts';
import { LocationSection } from './Location';
import { ReportsSection } from './Reports';
import { TimelineSection } from './Timeline';

const CLOSURE = ['resolved', 'false_report', 'no_action_required', 'handled_elsewhere', 'other'];
const ACTION_LABEL: Partial<Record<IncidentStatus, string>> = {
  under_review: 'Start review', verified: 'Verify', resolved: 'Mark resolved', closed: 'Close', unverified: 'Return to unverified',
};

function StatusActions({ incident }: { incident: IncidentDetail }) {
  const { can } = useAuth();
  const toast = useToast();
  const change = mutations.useChangeStatus(incident.id);
  const [target, setTarget] = useState<IncidentStatus | null>(null);
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  if (!can('incidents:update')) return null;
  const allowed = incident.allowed_statuses.filter((s) => s !== 'verified' || can('incidents:verify'));
  const label = (s: IncidentStatus) => {
    if (s === 'under_review' && incident.status === 'closed') return 'Reopen for review';
    if (s === 'under_review' && incident.status !== 'unverified') return 'Return to review';
    if (s === 'verified' && incident.status === 'resolved') return 'Reopen';
    return ACTION_LABEL[s] ?? INCIDENT_STATUS[s].label;
  };
  const needsConfirm = (s: IncidentStatus) => s === 'closed' || s === 'resolved' || s === 'unverified';
  const run = async (status: IncidentStatus, extra: { note?: string; closure_reason?: string } = {}) => {
    try {
      await change.mutateAsync({ status, ...extra });
      toast('success', `${incident.reference}: ${INCIDENT_STATUS[status].label}`);
      setTarget(null); setNote(''); setReason('');
    } catch (error) {
      toast('error', errorMessage(error));
    }
  };
  return (
    <div className="row-wrap">
      {allowed.map((s) => (
        <Button key={s} size="sm" variant={s === 'verified' ? 'primary' : 'default'} busy={change.isPending && change.variables?.status === s}
          onClick={() => (needsConfirm(s) ? setTarget(s) : run(s))}>
          {label(s)}
        </Button>
      ))}
      {target && (
        <Dialog open title={`${label(target)}: ${incident.reference}`} onClose={() => setTarget(null)}
          footer={<><Button onClick={() => setTarget(null)}>Cancel</Button>
            <Button variant="primary" busy={change.isPending}
              disabled={target === 'closed' && (!reason || ((reason === 'false_report' || reason === 'other') && !note.trim()))}
              onClick={() => run(target, { note: note || undefined, closure_reason: target === 'closed' ? reason : undefined })}>Confirm</Button></>}>
          {target === 'closed' && (
            <Field label="Reason" required>
              {(p) => <Select {...p} value={reason} onChange={(e) => setReason(e.target.value)}><option value="">Choose…</option>{CLOSURE.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}</Select>}
            </Field>
          )}
          <Field label="Note" required={target === 'closed' && (reason === 'false_report' || reason === 'other')}>
            {(p) => <Textarea {...p} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />}
          </Field>
        </Dialog>
      )}
    </div>
  );
}

export function IncidentHeader({ incident, onClose, compact }: { incident: IncidentDetail; onClose?: () => void; compact?: boolean }) {
  return (
    <div className="detail-section" style={{ gap: 'var(--s-2)' }}>
      <div className="spread">
        <div className="row-wrap">
          <h2 className="ref" style={{ fontSize: compact ? 'var(--text-lg)' : 'var(--text-xl)' }}>{incident.reference}</h2>
          <PriorityBadge priority={incident.priority} source={incident.priority_source} />
          <StatusBadge status={incident.status} />
        </div>
        <div className="row">
          {compact && <Link to={`/incidents/${incident.reference}`} className="btn btn-ghost btn-sm" title="Open full page"><ExternalLink size={14} /><span className="sr-only">Open full page</span></Link>}
          {onClose && <Button variant="ghost" size="sm" aria-label="Close details" icon={<X size={16} />} onClick={onClose} />}
        </div>
      </div>
      <span className="small muted">
        {humanize(incident.category)} · {incident.report_count} report{incident.report_count === 1 ? '' : 's'} · opened <TimeAgo value={incident.created_at} /> · updated <TimeAgo value={incident.updated_at} />
      </span>
      {incident.merged_into_id && <Callout>Merged into another incident. <Link to={`/incidents/${incident.merged_into_id}`}>Open it</Link></Callout>}
      <StatusActions incident={incident} />
    </div>
  );
}

export function IncidentPanel({ id, onClose }: { id: string; onClose?: () => void }) {
  const query = useIncident(id);
  if (query.isLoading) return <Loading label="Loading incident" />;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return <ErrorState title={missing ? 'Incident not found' : 'Could not load incident'} error={query.error} onRetry={missing ? undefined : () => void query.refetch()} />;
  }
  const incident = query.data!;
  return (
    <div aria-label={`Incident ${incident.reference}`}>
      <IncidentHeader incident={incident} onClose={onClose} compact />
      <FactsSection incident={incident} />
      <DispatchSection incident={incident} />
      <LocationSection incident={incident} />
      <DuplicatesSection incident={incident} />
      <ReportsSection incidentId={incident.id} />
      <TimelineSection incidentId={incident.id} />
    </div>
  );
}
