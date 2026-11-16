import { Check, MapPin, Search, X } from 'lucide-react';
import { useState } from 'react';

import { LazyMap } from '../../components/LazyMap';
import { Badge, Button, Callout, Dialog, Field, Input, Textarea, Unknown, useToast } from '../../components/ui';
import { ApiError, errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatCoordinates, formatDistance } from '../../lib/format';
import { LOCATION_SOURCE } from '../../lib/labels';
import { useOperation } from '../../lib/operation';
import { mutations } from '../../lib/queries';
import type { Coordinates, IncidentDetail, LocationCandidate } from '../../lib/types';

function CandidateRow({ incident, candidate }: { incident: IncidentDetail; candidate: LocationCandidate }) {
  const { can } = useAuth();
  const toast = useToast();
  const decide = mutations.useCandidateDecision(incident.id);
  const detail = candidate.source_detail;
  const run = async (decision: 'confirm' | 'reject') => {
    try {
      await decide.mutateAsync({ candidateId: candidate.id, decision });
      toast('success', decision === 'confirm' ? 'Position confirmed' : 'Candidate rejected');
    } catch (error) {
      toast('error', errorMessage(error));
    }
  };
  const status = candidate.verification_status;
  return (
    <li className="stack-sm" style={{ padding: '8px 0', opacity: status === 'rejected' || status === 'stale' ? 0.6 : 1 }}>
      <div className="spread">
        <div className="stack-sm" style={{ gap: 2, minWidth: 0 }}>
          <span style={{ fontWeight: 600 }} className="truncate">{candidate.label ?? <Unknown>Unnamed</Unknown>}</span>
          <span className="row-wrap xs">
            <Badge tone={candidate.source === 'operator' || candidate.source === 'caller_gps' ? 'tone-outline' : 'tag-machine'}>{LOCATION_SOURCE[candidate.source]}</Badge>
            {status === 'confirmed' && <Badge tone="tone-ok">Confirmed</Badge>}
            {status === 'rejected' && <Badge tone="tone-idle">Rejected</Badge>}
            {status === 'stale' && <Badge tone="tone-idle">Superseded</Badge>}
            {candidate.is_current && status !== 'confirmed' && <Badge tone="tone-accent">Shown on map</Badge>}
          </span>
          <span className="xs muted num">{formatCoordinates(candidate.coordinates.latitude, candidate.coordinates.longitude)}
            {candidate.uncertainty_radius_m != null && <> · ±{formatDistance(candidate.uncertainty_radius_m)}{detail.radius_basis === 'assumed' ? ' (assumed)' : ''}</>}
          </span>
          {typeof detail.matched_phrase === 'string' && (
            <span className="xs muted">
              Matched “<span className="script">{detail.matched_phrase}</span>” to landmark “{String(detail.landmark_name)}”
              {typeof detail.name_similarity === 'number' && <> (name similarity <span className="num">{(detail.name_similarity as number).toFixed(2)}</span>)</>}
            </span>
          )}
          {typeof detail.query === 'string' && <span className="xs muted">Geocoder result for “{detail.query}”. Importance is a ranking hint, not a probability.</span>}
        </div>
        {can('locations:confirm') && status !== 'confirmed' && status !== 'rejected' && incident.status !== 'duplicate' && (
          <div className="row">
            <Button size="sm" icon={<Check size={13} />} onClick={() => run('confirm')} disabled={decide.isPending} aria-label={`Confirm ${candidate.label ?? 'candidate'}`}>Confirm</Button>
            <Button size="sm" variant="ghost" icon={<X size={13} />} onClick={() => run('reject')} disabled={decide.isPending} aria-label={`Reject ${candidate.label ?? 'candidate'}`} />
          </div>
        )}
      </div>
    </li>
  );
}

function SetPositionDialog({ incident, onClose }: { incident: IncidentDetail; onClose: () => void }) {
  const toast = useToast();
  const { operation } = useOperation();
  const setLocation = mutations.useSetLocation(incident.id);
  const start = incident.location.coordinates;
  const [point, setPoint] = useState<Coordinates | null>(start);
  const [lat, setLat] = useState(start ? String(start.latitude) : '');
  const [lon, setLon] = useState(start ? String(start.longitude) : '');
  const [label, setLabel] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const pick = (p: Coordinates) => {
    setPoint(p);
    setLat(p.latitude.toFixed(6));
    setLon(p.longitude.toFixed(6));
  };
  const save = async () => {
    const latitude = Number(lat);
    const longitude = Number(lon);
    if (!lat || !lon || Number.isNaN(latitude) || Number.isNaN(longitude)) {
      setError('Enter coordinates or click the map.');
      return;
    }
    try {
      await setLocation.mutateAsync({ latitude, longitude, label: label || undefined, note: note || undefined });
      toast('success', 'Position set and confirmed');
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const preview = point ? [{ ...incident, location: { ...incident.location, coordinates: point, status: 'confirmed' as const, uncertainty_radius_m: null } }] : [];
  return (
    <Dialog open wide title={`Set position for ${incident.reference}`} onClose={onClose}
      description="Use this when you have established the position yourself, for example from the caller or a field team. It is recorded as operator-confirmed."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={setLocation.isPending} onClick={save}>Set position</Button></>}>
      <div style={{ height: 320, border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
        <LazyMap incidents={preview} center={point ?? operation?.map_center ?? null} picking onPick={pick} label="Pick a position" legendOpen={false} />
      </div>
      <div className="form-grid">
        <Field label="Latitude" required>{(p) => <Input {...p} inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} />}</Field>
        <Field label="Longitude" required>{(p) => <Input {...p} inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} />}</Field>
        <Field label="Label">{(p) => <Input {...p} maxLength={255} placeholder="e.g. house behind St Mary's school" value={label} onChange={(e) => setLabel(e.target.value)} />}</Field>
      </div>
      <Field label="How was this established?">{(p) => <Textarea {...p} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
      {error && <Callout tone="bad">{error}</Callout>}
    </Dialog>
  );
}

export function LocationSection({ incident }: { incident: IncidentDetail }) {
  const { can } = useAuth();
  const toast = useToast();
  const [setting, setSetting] = useState(false);
  const [phrase, setPhrase] = useState('');
  const landmark = mutations.useLandmarkSearch(incident.id);
  const geocode = mutations.useGeocode(incident.id);
  const editable = can('locations:confirm') && incident.status !== 'duplicate';
  const loc = incident.location;

  const search = async (kind: 'landmark' | 'geocode') => {
    if (phrase.trim().length < 3) return;
    const before = incident.location_candidates.length;
    try {
      const result = kind === 'landmark' ? await landmark.mutateAsync(phrase.trim()) : await geocode.mutateAsync(phrase.trim());
      const added = result.location_candidates.length - before;
      toast(added ? 'success' : 'info', added ? `${added} candidate${added === 1 ? '' : 's'} added` : 'No matches found');
    } catch (error) {
      toast('error', error instanceof ApiError && error.status === 503 ? 'No geocoder is configured for this deployment.' : errorMessage(error));
    }
  };

  return (
    <section className="detail-section" aria-labelledby="loc-h">
      <div className="spread">
        <h3 id="loc-h" className="section-title">Location</h3>
        {editable && <Button size="sm" icon={<MapPin size={13} />} onClick={() => setSetting(true)}>Set position</Button>}
      </div>
      <dl className="kv">
        <dt>Caller's description</dt>
        <dd className="script">{loc.description ?? <Unknown>None recorded</Unknown>}</dd>
        <dt>Position</dt>
        <dd>
          {loc.status === 'none' && <Unknown>Not established</Unknown>}
          {loc.status !== 'none' && loc.coordinates && (
            <div className="stack-sm" style={{ gap: 2 }}>
              <span className="row-wrap">
                <Badge tone={loc.status === 'confirmed' ? 'tone-ok' : 'tone-warn'}>{loc.status === 'confirmed' ? 'Confirmed' : 'Unconfirmed candidate'}</Badge>
                {loc.source && <span className="small muted">{LOCATION_SOURCE[loc.source]}</span>}
              </span>
              {loc.label && <span>{loc.label}</span>}
              <span className="xs muted num">{formatCoordinates(loc.coordinates.latitude, loc.coordinates.longitude)}{loc.uncertainty_radius_m != null && ` · ±${formatDistance(loc.uncertainty_radius_m)}`}</span>
            </div>
          )}
        </dd>
      </dl>
      {loc.status === 'candidate' && (
        <Callout tone="warn">This position is a candidate that no one has confirmed. Distances and recommendations are measured to it.</Callout>
      )}
      {incident.location_candidates.length > 0 && (
        <div className="stack-sm">
          <span className="small muted">Evidence ({incident.location_candidates.length})</span>
          <ul className="list">{incident.location_candidates.map((c) => <CandidateRow key={c.id} incident={incident} candidate={c} />)}</ul>
        </div>
      )}
      {editable && (
        <form className="stack-sm" onSubmit={(e) => { e.preventDefault(); void search('landmark'); }}>
          <label htmlFor={`lm-${incident.id}`} className="small muted">Look up a place mentioned by the caller</label>
          <div className="row">
            <Input id={`lm-${incident.id}`} value={phrase} onChange={(e) => setPhrase(e.target.value)} placeholder="e.g. old bridge, St Mary's school" />
            <Button type="submit" size="sm" icon={<Search size={13} />} busy={landmark.isPending} disabled={phrase.trim().length < 3}>Landmarks</Button>
            <Button size="sm" busy={geocode.isPending} disabled={phrase.trim().length < 3} onClick={() => void search('geocode')}>Geocoder</Button>
          </div>
          <span className="xs faint">Results are added as candidates for you to confirm or reject. Nothing becomes the position automatically.</span>
        </form>
      )}
      {setting && <SetPositionDialog incident={incident} onClose={() => setSetting(false)} />}
    </section>
  );
}
