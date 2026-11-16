import { Crosshair, Pencil, Plus, Truck } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { LazyMap } from '../../components/LazyMap';
import { Badge, Button, Callout, Dialog, EmptyState, ErrorState, Field, Input, Loading, PageHeader, Panel, Select, Textarea, TimeAgo, Unknown, useToast } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatAge, formatCoordinates, humanize } from '../../lib/format';
import { RESOURCE_STATUS } from '../../lib/labels';
import { useOperation } from '../../lib/operation';
import { mutations, useResourceOptions, useResources } from '../../lib/queries';
import type { Coordinates, Resource } from '../../lib/types';
import { RequireOperation } from '../NoOperation';

const STALE_MS = 2 * 60 * 60 * 1000;

function ResourceForm({ resource, onClose }: { resource?: Resource; onClose: () => void }) {
  const { operation } = useOperation();
  const toast = useToast();
  const options = useResourceOptions();
  const create = mutations.useCreateResource();
  const update = mutations.useUpdateResource(resource?.id ?? '');
  const [callsign, setCallsign] = useState(resource?.callsign ?? '');
  const [type, setType] = useState(resource?.resource_type ?? 'boat');
  const [name, setName] = useState(resource?.name ?? '');
  const [capacity, setCapacity] = useState(resource?.capacity != null ? String(resource.capacity) : '');
  const [crew, setCrew] = useState(resource?.crew_size != null ? String(resource.crew_size) : '');
  const [caps, setCaps] = useState<string[]>(resource?.declared_capabilities ?? []);
  const [base, setBase] = useState(resource?.base_name ?? '');
  const [contact, setContact] = useState(resource?.contact ?? '');
  const [notes, setNotes] = useState(resource?.notes ?? '');
  const [error, setError] = useState<string | null>(null);
  const defaults = options.data?.default_capabilities[type] ?? [];
  const submit = async () => {
    const body: Record<string, unknown> = {
      resource_type: type, name, capacity: capacity ? Number(capacity) : null, crew_size: crew ? Number(crew) : null,
      capabilities: caps, base_name: base, notes,
    };
    if (!resource?.contact_redacted) body.contact = contact;
    try {
      if (resource) await update.mutateAsync(body);
      else await create.mutateAsync({ ...body, disaster_id: operation!.id, callsign });
      toast('success', resource ? `${resource.callsign} updated` : `${callsign.toUpperCase()} registered`);
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  return (
    <Dialog open wide title={resource ? `Edit ${resource.callsign}` : 'Register a resource'} onClose={onClose}
      description="Enter only resources that actually exist and are available to this operation."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={create.isPending || update.isPending} disabled={!name.trim() || (!resource && callsign.trim().length < 2)} onClick={submit}>{resource ? 'Save' : 'Register'}</Button></>}>
      <div className="form-grid">
        {!resource && <Field label="Callsign" required hint="Short radio identifier, e.g. BOAT-3">{(p) => <Input {...p} maxLength={64} value={callsign} onChange={(e) => setCallsign(e.target.value.toUpperCase())} />}</Field>}
        <Field label="Type" required>{(p) => <Select {...p} value={type} onChange={(e) => setType(e.target.value)}>{(options.data?.types ?? [type]).map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</Select>}</Field>
        <Field label="Name" required>{(p) => <Input {...p} maxLength={255} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Fire & Rescue boat, Aluva station" />}</Field>
        <Field label="Capacity (people)">{(p) => <Input {...p} type="number" min={0} value={capacity} onChange={(e) => setCapacity(e.target.value)} />}</Field>
        <Field label="Crew">{(p) => <Input {...p} type="number" min={0} value={crew} onChange={(e) => setCrew(e.target.value)} />}</Field>
        <Field label="Base">{(p) => <Input {...p} maxLength={255} value={base} onChange={(e) => setBase(e.target.value)} />}</Field>
        <Field label="Contact" hint={resource?.contact_redacted ? 'Hidden for your role' : 'Radio channel or phone'}>
          {(p) => <Input {...p} maxLength={160} disabled={resource?.contact_redacted} value={contact} onChange={(e) => setContact(e.target.value)} />}
        </Field>
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }} className="stack-sm">
        <legend className="label">Capabilities</legend>
        <span className="xs muted">If none are ticked, the defaults for the type apply{defaults.length ? `: ${defaults.map(humanize).join(', ')}` : ''}.</span>
        <div className="row-wrap">
          {(options.data?.capabilities ?? []).map((c) => (
            <label key={c} className="checkbox"><input type="checkbox" checked={caps.includes(c)} onChange={(e) => setCaps((all) => (e.target.checked ? [...all, c] : all.filter((x) => x !== c)))} />{humanize(c)}</label>
          ))}
        </div>
      </fieldset>
      <Field label="Notes">{(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
      {error && <Callout tone="bad">{error}</Callout>}
    </Dialog>
  );
}

function StatusDialog({ resource, onClose }: { resource: Resource; onClose: () => void }) {
  const toast = useToast();
  const setStatus = mutations.useResourceStatus(resource.id);
  const retire = mutations.useRetireResource(resource.id);
  type Manual = 'available' | 'maintenance' | 'offline';
  const [status, setStatusValue] = useState<Manual>(resource.status === 'assigned' ? 'available' : resource.status);
  const [note, setNote] = useState(resource.status_note ?? '');
  const [retiring, setRetiring] = useState(false);
  const committed = resource.status === 'assigned';
  const save = async () => {
    try {
      if (retiring) await retire.mutateAsync(note);
      else await setStatus.mutateAsync({ status, note: note || undefined });
      toast('success', `${resource.callsign} updated`);
      onClose();
    } catch (e) {
      toast('error', errorMessage(e));
    }
  };
  return (
    <Dialog open title={`Availability: ${resource.callsign}`} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant={retiring ? 'danger' : 'primary'} disabled={committed || ((status !== 'available' || retiring) && !note.trim())} busy={setStatus.isPending || retire.isPending} onClick={save}>{retiring ? 'Retire resource' : 'Save'}</Button></>}>
      {committed && <Callout tone="warn">This resource is committed to {resource.current_assignment?.incident_reference}. Complete or cancel that assignment first.</Callout>}
      {!committed && (
        <>
          <Field label="Status">{(p) => <Select {...p} value={status} disabled={retiring} onChange={(e) => setStatusValue(e.target.value as Manual)}>{(['available', 'maintenance', 'offline'] as const).map((s) => <option key={s} value={s}>{RESOURCE_STATUS[s].label}</option>)}</Select>}</Field>
          <Field label="Note" required={status !== 'available' || retiring}>{(p) => <Textarea {...p} rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. engine repair until 18:00" />}</Field>
          <label className="checkbox small"><input type="checkbox" checked={retiring} onChange={(e) => setRetiring(e.target.checked)} />Retire permanently (history is kept)</label>
        </>
      )}
    </Dialog>
  );
}

function PositionDialog({ resource, onClose }: { resource: Resource; onClose: () => void }) {
  const toast = useToast();
  const { operation } = useOperation();
  const update = mutations.useResourcePosition(resource.id);
  const [point, setPoint] = useState<Coordinates | null>(resource.position?.coordinates ?? null);
  const [lat, setLat] = useState(point ? String(point.latitude) : '');
  const [lon, setLon] = useState(point ? String(point.longitude) : '');
  const [when, setWhen] = useState('');
  const pick = (p: Coordinates) => { setPoint(p); setLat(p.latitude.toFixed(6)); setLon(p.longitude.toFixed(6)); };
  const save = async () => {
    try {
      await update.mutateAsync({ latitude: Number(lat), longitude: Number(lon), source: 'operator', reported_at: when ? new Date(when).toISOString() : undefined });
      toast('success', `${resource.callsign} position recorded`);
      onClose();
    } catch (e) {
      toast('error', errorMessage(e));
    }
  };
  return (
    <Dialog open wide title={`Report position: ${resource.callsign}`} onClose={onClose}
      description="Record where the resource was reported to be. It is stored as operator-entered with the time you give."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={update.isPending} disabled={!lat || !lon} onClick={save}>Record position</Button></>}>
      <div style={{ height: 320 }}><LazyMap incidents={[]} resources={point ? [{ ...resource, position: { coordinates: point, source: 'operator', reported_at: new Date().toISOString(), accuracy_m: null } }] : []} center={point ?? operation!.map_center} picking onPick={pick} label="Pick resource position" legendOpen={false} /></div>
      <div className="form-grid">
        <Field label="Latitude" required>{(p) => <Input {...p} inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} />}</Field>
        <Field label="Longitude" required>{(p) => <Input {...p} inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} />}</Field>
        <Field label="Reported at" hint="Leave empty for now">{(p) => <Input {...p} type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />}</Field>
      </div>
    </Dialog>
  );
}

function Register() {
  const { operation } = useOperation();
  const { can } = useAuth();
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [retired, setRetired] = useState(false);
  const [editing, setEditing] = useState<Resource | 'new' | null>(null);
  const [statusFor, setStatusFor] = useState<Resource | null>(null);
  const [positionFor, setPositionFor] = useState<Resource | null>(null);
  const resources = useResources({ disaster_id: operation!.id, status: status ? [status] : undefined, q: q || undefined, include_retired: retired });
  const manage = can('resources:manage');
  const items = resources.data?.items ?? [];
  const counts = items.reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.status]: (acc[r.status] ?? 0) + 1 }), {});
  return (
    <div className="page page-wide">
      <PageHeader title="Resources" description="Teams, boats and vehicles available to this operation, with their last reported position."
        actions={manage && <Button variant="primary" icon={<Plus size={14} />} onClick={() => setEditing('new')}>Register resource</Button>} />
      <div className="grid-2">
        <Panel flush title={
          <div className="row-wrap">
            <label className="sr-only" htmlFor="res-q">Search</label>
            <Input id="res-q" type="search" placeholder="Callsign, name, base" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 200 }} />
            <label className="sr-only" htmlFor="res-st">Status</label>
            <Select id="res-st" value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: 'auto' }}>
              <option value="">Any status</option>{Object.entries(RESOURCE_STATUS).map(([v, m]) => <option key={v} value={v}>{m.label}</option>)}
            </Select>
            <label className="checkbox small"><input type="checkbox" checked={retired} onChange={(e) => setRetired(e.target.checked)} />Retired</label>
          </div>
        } footer={resources.data && <span className="small muted num">{Object.entries(counts).map(([s, n]) => `${n} ${RESOURCE_STATUS[s as Resource['status']].label.toLowerCase()}`).join(' · ') || '0 resources'}</span>}>
          {resources.isLoading && <Loading />}
          {resources.isError && <ErrorState error={resources.error} onRetry={() => void resources.refetch()} />}
          {resources.data && items.length === 0 && (
            <EmptyState icon={<Truck size={28} />} title="No resources registered" action={manage && <Button variant="primary" onClick={() => setEditing('new')}>Register the first resource</Button>}>
              Recommendations need resources with capabilities and positions.
            </EmptyState>
          )}
          {items.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Resource</th><th>Status</th><th>Capabilities</th><th>Capacity</th><th>Position</th>{manage && <th><span className="sr-only">Actions</span></th>}</tr></thead>
                <tbody>
                  {items.map((r) => {
                    const stale = r.position && Date.now() - Date.parse(r.position.reported_at) > STALE_MS;
                    return (
                      <tr key={r.id} style={{ opacity: r.is_retired ? 0.55 : 1 }}>
                        <td><strong>{r.callsign}</strong><div className="xs muted">{r.name} · {humanize(r.resource_type)}</div>{r.contact && <div className="xs num">{r.contact}</div>}</td>
                        <td>
                          <Badge tone={RESOURCE_STATUS[r.status].tone}>{r.is_retired ? 'Retired' : RESOURCE_STATUS[r.status].label}</Badge>
                          {r.current_assignment && <div className="xs"><Link to={`/?incident=${r.current_assignment.incident_id}`} className="num">{r.current_assignment.incident_reference}</Link></div>}
                          {r.status_note && <div className="xs muted">{r.status_note}</div>}
                        </td>
                        <td className="xs">{r.capabilities.map(humanize).join(', ') || <Unknown>none</Unknown>}{!r.declared_capabilities.length && r.capabilities.length > 0 && <div className="faint">type defaults</div>}</td>
                        <td className="num">{r.capacity ?? <Unknown>—</Unknown>}</td>
                        <td className="small">
                          {r.position ? (
                            <div className="stack-sm" style={{ gap: 0 }}>
                              <span className="num xs">{formatCoordinates(r.position.coordinates.latitude, r.position.coordinates.longitude)}</span>
                              <span className="xs" style={{ color: stale ? 'var(--warn)' : undefined }} title={r.position.reported_at}>{formatAge(r.position.reported_at)} ago · {humanize(r.position.source ?? 'unknown')}</span>
                            </div>
                          ) : <Unknown>Not reported</Unknown>}
                        </td>
                        {manage && (
                          <td>
                            {!r.is_retired && (
                              <div className="row">
                                <Button size="sm" variant="ghost" aria-label={`Report position of ${r.callsign}`} title="Report position" icon={<Crosshair size={14} />} onClick={() => setPositionFor(r)} />
                                <Button size="sm" variant="ghost" aria-label={`Edit ${r.callsign}`} title="Edit" icon={<Pencil size={14} />} onClick={() => setEditing(r)} />
                                <Button size="sm" onClick={() => setStatusFor(r)}>Availability</Button>
                              </div>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <Panel flush title="Positions" actions={resources.dataUpdatedAt > 0 && <span className="xs muted">updated <TimeAgo value={resources.dataUpdatedAt} /></span>}>
          <div style={{ height: 480 }}>
            <LazyMap incidents={[]} resources={items.filter((r) => !r.is_retired)} center={operation!.map_center} label="Resource positions" />
          </div>
          <div className="panel-footer xs faint">Positions are shown as last reported. Grey markers are more than 2 hours old.</div>
        </Panel>
      </div>
      {editing && <ResourceForm resource={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
      {statusFor && <StatusDialog resource={statusFor} onClose={() => setStatusFor(null)} />}
      {positionFor && <PositionDialog resource={positionFor} onClose={() => setPositionFor(null)} />}
    </div>
  );
}

export function ResourcesPage() {
  return <RequireOperation><Register /></RequireOperation>;
}
