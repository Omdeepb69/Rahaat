/**
 * Public emergency report form. Works only when the server has public intake
 * enabled. Submits to the rate-limited /public endpoints; no sign-in.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Logo } from '../../components/Shell';
import { Button, Callout, Field, Input, Loading, Select, Textarea } from '../../components/ui';
import { ApiError, errorMessage, request } from '../../lib/api';
import { formatFull, newIdempotencyKey } from '../../lib/format';

interface PublicOperation { id: string; name: string }
interface Ticket { ticket: string; received_at: string; stage?: string; message?: string }

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <main className="auth-single" lang="en">
      <div className="panel">
        <div className="panel-header"><span className="brand"><Logo /> RAAHAT</span><span className="xs muted">Emergency report</span></div>
        <div className="panel-body">{children}</div>
      </div>
    </main>
  );
}

export function PublicReportPage() {
  const [operations, setOperations] = useState<PublicOperation[] | null>(null);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [operationId, setOperationId] = useState('');
  const [text, setText] = useState('');
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [place, setPlace] = useState('');
  const [people, setPeople] = useState('');
  const [gps, setGps] = useState<{ latitude: number; longitude: number; accuracy: number } | null>(null);
  const [gpsState, setGpsState] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const token = useRef(newIdempotencyKey());

  useEffect(() => {
    document.title = 'Report an emergency · RAAHAT';
    request<PublicOperation[]>('/api/v1/public/operations', { auth: false })
      .then((ops) => { setOperations(ops); setOperationId(ops[0]?.id ?? ''); })
      .catch((e) => setUnavailable(e instanceof ApiError && e.status === 404
        ? 'Online reporting is not enabled for this service.'
        : 'The reporting service cannot be reached right now.'));
  }, []);

  const locate = () => {
    if (!navigator.geolocation) { setGpsState('This device cannot share its location.'); return; }
    setGpsState('Finding your location…');
    navigator.geolocation.getCurrentPosition(
      (pos) => { setGps({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy }); setGpsState(null); },
      () => setGpsState('Location was not shared. Describe the place instead.'),
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
    );
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) { setError('Describe what is happening.'); return; }
    setBusy(true);
    setError(null);
    try {
      const result = await request<Ticket>('/api/v1/public/reports', {
        method: 'POST', auth: false,
        body: {
          disaster_id: operationId, situation_description: text.trim(), phone_number: phone || undefined,
          caller_name: name || undefined, location_text: place || undefined,
          people_count: people ? Number(people) : undefined,
          latitude: gps?.latitude, longitude: gps?.longitude, submission_token: token.current,
        },
      });
      setTicket(result);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (unavailable) return <Frame><Callout tone="warn" title="Not available">{unavailable} In an emergency call 112.</Callout></Frame>;
  if (!operations) return <Frame><Loading /></Frame>;
  if (ticket) {
    return (
      <Frame>
        <div className="stack" role="status">
          <h1>Report received</h1>
          <p>Your report was received at {formatFull(ticket.received_at)}. Keep this reference to check its status:</p>
          <p className="ref" style={{ fontSize: 'var(--text-lg)', wordBreak: 'break-all' }}>{ticket.ticket}</p>
          <Link className="btn btn-primary" to={`/report/status/${ticket.ticket}`}>Check status</Link>
          <Callout tone="warn">This does not replace calling emergency services. If life is in danger, call 112.</Callout>
        </div>
      </Frame>
    );
  }
  return (
    <Frame>
      <form className="stack" onSubmit={submit} noValidate>
        <h1>Report an emergency</h1>
        <Callout tone="warn">If life is in immediate danger, call 112. This form goes to the disaster control room.</Callout>
        {operations.length === 0 ? <Callout>No response is accepting online reports at the moment.</Callout> : (
          <>
            {operations.length > 1 && (
              <Field label="Response">{(p) => <Select {...p} value={operationId} onChange={(e) => setOperationId(e.target.value)}>{operations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select>}</Field>
            )}
            <Field label="What is happening?" required hint="Any language. Who needs help, how many people, water level, injuries.">
              {(p) => <Textarea {...p} className="textarea script" rows={5} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />}
            </Field>
            <Field label="Where?" hint="Nearest landmark: school, temple, bridge, junction, ward number.">
              {(p) => <Input {...p} className="input script" maxLength={500} value={place} onChange={(e) => setPlace(e.target.value)} />}
            </Field>
            <div className="row-wrap">
              <Button onClick={locate}>Share my location</Button>
              {gps && <span className="small">Location shared (accurate to about {Math.round(gps.accuracy)} m)</span>}
              {gpsState && <span className="small muted">{gpsState}</span>}
            </div>
            <div className="form-grid">
              <Field label="Number of people">{(p) => <Input {...p} type="number" min={1} inputMode="numeric" value={people} onChange={(e) => setPeople(e.target.value)} />}</Field>
              <Field label="Phone number" hint="So the control room can call back.">{(p) => <Input {...p} type="tel" maxLength={20} value={phone} onChange={(e) => setPhone(e.target.value)} />}</Field>
              <Field label="Your name">{(p) => <Input {...p} maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
            </div>
            {error && <Callout tone="bad">{error}</Callout>}
            <Button type="submit" variant="primary" busy={busy}>Send report</Button>
          </>
        )}
      </form>
    </Frame>
  );
}

export function PublicTicketPage() {
  const { ticket = '' } = useParams();
  const [status, setStatus] = useState<Ticket | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const load = () => request<Ticket>(`/api/v1/public/tickets/${encodeURIComponent(ticket)}`, { auth: false })
      .then((t) => { setStatus(t); setError(null); }).catch((e) => setError(errorMessage(e)));
    void load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [ticket]);
  return (
    <Frame>
      <div className="stack" role="status" aria-live="polite">
        <h1>Report status</h1>
        {error && <Callout tone="bad">{error}</Callout>}
        {!status && !error && <Loading />}
        {status && <><p style={{ fontSize: 'var(--text-lg)' }}>{status.message}</p><p className="small muted">Received {formatFull(status.received_at)}. This page refreshes every 30 seconds.</p></>}
        <Link to="/report">Send another report</Link>
      </div>
    </Frame>
  );
}
