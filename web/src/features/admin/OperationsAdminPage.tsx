import { MapPin, Plus } from 'lucide-react';
import { useState } from 'react';

import { JurisdictionPicker, type Picked } from '../../components/JurisdictionPicker';
import { LazyMap } from '../../components/LazyMap';
import { Badge, Button, Callout, Dialog, EmptyState, ErrorState, Field, Input, Loading, PageHeader, Panel, Select, Textarea, useToast } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatCoordinates, formatDateTime, humanize } from '../../lib/format';
import { useOperation } from '../../lib/operation';
import { mutations } from '../../lib/queries';
import type { Coordinates, Operation } from '../../lib/types';

const TYPES = ['flood', 'cyclone', 'landslide', 'earthquake', 'fire', 'infrastructure', 'other'];

function OperationForm({ existing, onClose }: { existing?: Operation; onClose: () => void }) {
  const toast = useToast();
  const { select } = useOperation();
  const create = mutations.useCreateOperation();
  const update = mutations.useUpdateOperation(existing?.id ?? '');
  const [name, setName] = useState(existing?.name ?? '');
  const [type, setType] = useState(existing?.disaster_type ?? 'flood');
  const [area, setArea] = useState(existing?.area_name ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [center, setCenter] = useState<Coordinates | null>(existing?.map_center ?? null);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();
  const own = user?.jurisdiction;
  const [place, setPlace] = useState<Picked>({ state: own?.state_code ?? '', district: own?.district_code ?? '' });
  const placeReady = existing || own?.level === 'district' || !!place.state;
  const save = async () => {
    try {
      if (existing) {
        await update.mutateAsync({ name, area_name: area, description, map_center: center });
      } else {
        const created = await create.mutateAsync({
          name, disaster_type: type, area_name: area || undefined, description: description || undefined, map_center: center ?? undefined,
          state_code: place.state || undefined, district_code: place.district || undefined,
        });
        select(created.id);
      }
      toast('success', existing ? 'Operation updated' : `Operation "${name}" opened`);
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  return (
    <Dialog open wide title={existing ? `Edit ${existing.name}` : 'Open an operation'} onClose={onClose}
      description="An operation groups the reports, incidents and resources of one response."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={name.trim().length < 3 || !placeReady} busy={create.isPending || update.isPending} onClick={save}>{existing ? 'Save' : 'Open operation'}</Button></>}>
      <div className="form-grid">
        <Field label="Name" required>{(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ernakulam monsoon flooding, Nov 2026" />}</Field>
        {!existing && <Field label="Type">{(p) => <Select {...p} value={type} onChange={(e) => setType(e.target.value)}>{TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</Select>}</Field>}
        <Field label="Area">{(p) => <Input {...p} value={area} onChange={(e) => setArea(e.target.value)} placeholder="District or region" />}</Field>
      </div>
      {!existing && own?.level === 'district' && <p className="small muted">The operation will belong to {own.label}.</p>}
      {!existing && own && own.level !== 'district' && (
        <div className="stack-sm">
          <span className="label">Jurisdiction</span>
          <span className="xs muted">Only control rooms for this area will see the operation. Public reports from a district go to its newest active operation.</span>
          <JurisdictionPicker value={place} onChange={setPlace} fixedState={own.level === 'state' ? own.state_code : null} stateWideLabel="Whole state" />
        </div>
      )}
      {existing && <p className="small muted">Jurisdiction: {existing.jurisdiction}</p>}
      <Field label="Description">{(p) => <Textarea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
      <div className="stack-sm">
        <span className="label">Map focus</span>
        <span className="xs muted">Click the map to set where maps open and where landmark searches are focused (within 75 km).</span>
        <div style={{ height: 300 }}><LazyMap incidents={[]} center={center} picking onPick={setCenter} label="Pick the operation's map focus" legendOpen={false} /></div>
        <span className="small num">{center ? formatCoordinates(center.latitude, center.longitude) : 'Not set'}</span>
      </div>
      {error && <Callout tone="bad">{error}</Callout>}
    </Dialog>
  );
}

function CloseButton({ operation }: { operation: Operation }) {
  const toast = useToast();
  const update = mutations.useUpdateOperation(operation.id);
  const [confirm, setConfirm] = useState(false);
  const next = operation.status === 'active' ? 'closed' : 'active';
  return (
    <>
      <Button size="sm" onClick={() => setConfirm(true)}>{next === 'closed' ? 'Close' : 'Reopen'}</Button>
      <Dialog open={confirm} title={`${next === 'closed' ? 'Close' : 'Reopen'} ${operation.name}?`} onClose={() => setConfirm(false)}
        description={next === 'closed' ? 'A closed operation keeps all its records but no longer accepts reports.' : 'The operation will accept reports again.'}
        footer={<><Button onClick={() => setConfirm(false)}>Cancel</Button><Button variant="primary" busy={update.isPending}
          onClick={async () => { try { await update.mutateAsync({ status: next }); toast('success', 'Operation updated'); setConfirm(false); } catch (e) { toast('error', errorMessage(e)); } }}>Confirm</Button></>}>
        {operation.open_incidents > 0 && next === 'closed' && <Callout tone="warn">{operation.open_incidents} incident(s) are still open.</Callout>}
      </Dialog>
    </>
  );
}

export function OperationsAdminPage() {
  const { operations, loading, error } = useOperation();
  const [editing, setEditing] = useState<Operation | 'new' | null>(null);
  return (
    <div className="page">
      <PageHeader title="Operations setup" actions={<Button variant="primary" icon={<Plus size={14} />} onClick={() => setEditing('new')}>Open operation</Button>} />
      <Panel flush>
        {loading && <Loading />}
        {!!error && <ErrorState error={error} />}
        {!loading && operations.length === 0 && <EmptyState title="No operations yet" action={<Button variant="primary" onClick={() => setEditing('new')}>Open the first operation</Button>} />}
        {operations.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Operation</th><th>Jurisdiction</th><th>Status</th><th>Open incidents</th><th>Resources</th><th>Map focus</th><th>Opened</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {operations.map((o) => (
                  <tr key={o.id}>
                    <td><strong>{o.name}</strong><div className="xs muted">{humanize(o.disaster_type)}{o.area_name && ` · ${o.area_name}`}</div></td>
                    <td className="small">{o.jurisdiction}</td>
                    <td className="row-wrap"><Badge tone={o.status === 'active' ? 'tone-ok' : 'tone-idle'}>{humanize(o.status)}</Badge>{o.is_standing && <Badge tone="tone-accent">Public reports</Badge>}</td>
                    <td className="num">{o.open_incidents}</td>
                    <td className="num">{o.resources}</td>
                    <td className="small">{o.map_center ? <span className="row num"><MapPin size={12} aria-hidden />{formatCoordinates(o.map_center.latitude, o.map_center.longitude)}</span> : <span className="faint">not set</span>}</td>
                    <td className="small num">{formatDateTime(o.started_at ?? o.created_at)}</td>
                    <td><div className="row"><Button size="sm" onClick={() => setEditing(o)}>Edit</Button><CloseButton operation={o} /></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {editing && <OperationForm existing={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
