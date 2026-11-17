import { CheckCircle2, MapPin } from 'lucide-react';
import { useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { LazyMap } from '../../components/LazyMap';
import { Button, Callout, Dialog, Field, Input, PageHeader, Panel, Select, Textarea } from '../../components/ui';
import { ApiError, errorMessage, NetworkError } from '../../lib/api';
import { formatCoordinates, newIdempotencyKey } from '../../lib/format';
import { LANGUAGES, RECEIVED_VIA } from '../../lib/labels';
import { useOperation } from '../../lib/operation';
import { mutations } from '../../lib/queries';
import type { Coordinates, CreatedReport } from '../../lib/types';
import { RequireOperation } from '../NoOperation';

interface FormState {
  text: string;
  received_via: string;
  language_hint: string;
  caller_name: string;
  caller_contact: string;
  location_text: string;
  people_count: string;
  position: Coordinates | null;
}

const EMPTY: FormState = {
  text: '', received_via: 'phone_call', language_hint: '', caller_name: '', caller_contact: '',
  location_text: '', people_count: '', position: null,
};

function Result({ result, onAnother }: { result: CreatedReport; onAnother: () => void }) {
  return (
    <Panel title="Report recorded" id="result-h">
      <div className="stack" role="status">
        <div className="row"><CheckCircle2 size={20} style={{ color: 'var(--ok)' }} aria-hidden />
          <span>
            {result.already_existed ? 'This report had already been recorded; nothing was duplicated. ' : ''}
            {result.is_new_incident ? 'A new incident was opened: ' : 'The report was attached to incident '}
            <Link to={`/control/incidents/${result.incident_reference}`} className="ref" style={{ fontWeight: 700 }}>{result.incident_reference}</Link>
          </span>
        </div>
        <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
          <li>The incident is <strong>unverified</strong> until someone confirms it.</li>
          <li>{result.duplicate_candidates ? <><strong className="num">{result.duplicate_candidates}</strong> possible duplicate{result.duplicate_candidates === 1 ? '' : 's'} found and held for review. Nothing was merged.</> : 'No possible duplicates were found.'}</li>
          <li>{result.location_candidates ? <><strong className="num">{result.location_candidates}</strong> location candidate{result.location_candidates === 1 ? '' : 's'} found from places mentioned. Confirm one on the incident.</> : 'No location candidates were found from the text.'}</li>
          {result.enrichment_pending && <li>Translation and model extraction will be added shortly by the background worker.</li>}
        </ul>
        <div className="row-wrap">
          <Link className="btn btn-primary" to={`/control/control?incident=${result.incident_id}`}>Open on board</Link>
          <Button onClick={onAnother}>Enter another report</Button>
        </div>
      </div>
    </Panel>
  );
}

function Form() {
  const { operation } = useOperation();
  const create = mutations.useCreateReport();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [result, setResult] = useState<CreatedReport | null>(null);
  const [error, setError] = useState<{ message: string; fields: Record<string, string>; network: boolean } | null>(null);
  const [picking, setPicking] = useState(false);
  // One key per report. A retry after a timeout reuses it, so the server
  // returns the first copy instead of creating a second.
  const key = useRef(newIdempotencyKey());
  const textRef = useRef<HTMLTextAreaElement>(null);

  const set = <K extends keyof FormState>(field: K, value: FormState[K]) => setForm((f) => ({ ...f, [field]: value }));
  const closed = operation!.status === 'closed';

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!form.text.trim()) {
      setError({ message: '', fields: { text: 'Enter what the caller reported.' }, network: false });
      textRef.current?.focus();
      return;
    }
    setError(null);
    try {
      const created = await create.mutateAsync({
        disaster_id: operation!.id,
        idempotency_key: key.current,
        text: form.text,
        received_via: form.received_via,
        language_hint: form.language_hint || undefined,
        caller_name: form.caller_name || undefined,
        caller_contact: form.caller_contact || undefined,
        location_text: form.location_text || undefined,
        people_count: form.people_count ? Number(form.people_count) : undefined,
        latitude: form.position?.latitude,
        longitude: form.position?.longitude,
      });
      setResult(created);
    } catch (e) {
      const fields: Record<string, string> = {};
      if (e instanceof ApiError) e.fields.forEach((f) => (fields[f.field] = f.message));
      setError({ message: errorMessage(e), fields, network: e instanceof NetworkError });
    }
  };

  const another = () => {
    key.current = newIdempotencyKey();
    setForm(EMPTY);
    setResult(null);
    setTimeout(() => textRef.current?.focus(), 0);
  };

  if (result) return <div className="page"><PageHeader title="New report" /><Result result={result} onAnother={another} /></div>;

  return (
    <div className="page">
      <PageHeader title="New report" description={<>Record what was reported, in the caller's own words and language. Facts are extracted automatically and shown for you to check. Operation: <strong>{operation!.name}</strong></>} />
      {closed && <Callout tone="warn">This operation is closed and does not accept reports.</Callout>}
      <form className="stack-lg" onSubmit={submit} onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void submit(); }} noValidate>
        <Panel title="What was reported">
          <div className="stack">
            <Field label="Report" required error={error?.fields.text ?? null}
              hint="Type it as said, in any language (Malayalam, English, Hindi, Konkani). Ctrl+Enter submits.">
              {(p) => <Textarea {...p} ref={textRef} className="textarea script" rows={6} maxLength={5000} value={form.text} onChange={(e) => set('text', e.target.value)} autoFocus />}
            </Field>
            <div className="form-grid">
              <Field label="Received by">
                {(p) => <Select {...p} value={form.received_via} onChange={(e) => set('received_via', e.target.value)}>{Object.entries(RECEIVED_VIA).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>}
              </Field>
              <Field label="Language" hint="Leave on automatic unless you know it.">
                {(p) => (
                  <Select {...p} value={form.language_hint} onChange={(e) => set('language_hint', e.target.value)}>
                    <option value="">Identify automatically</option>
                    {['ml', 'en', 'hi', 'kok'].map((c) => <option key={c} value={c}>{LANGUAGES[c]}</option>)}
                  </Select>
                )}
              </Field>
              <Field label="Number of people" hint="Only if the caller said." error={error?.fields.people_count ?? null}>
                {(p) => <Input {...p} type="number" min={1} inputMode="numeric" value={form.people_count} onChange={(e) => set('people_count', e.target.value)} />}
              </Field>
            </div>
          </div>
        </Panel>
        <Panel title="Caller">
          <div className="form-grid">
            <Field label="Name">{(p) => <Input {...p} maxLength={160} autoComplete="off" value={form.caller_name} onChange={(e) => set('caller_name', e.target.value)} />}</Field>
            <Field label="Phone or contact" hint="Used to recognise repeat calls from the same household.">
              {(p) => <Input {...p} maxLength={64} inputMode="tel" autoComplete="off" value={form.caller_contact} onChange={(e) => set('caller_contact', e.target.value)} />}
            </Field>
          </div>
        </Panel>
        <Panel title="Where">
          <div className="stack">
            <Field label="Place as described" hint="e.g. behind the school near the old bridge, ward 4. Landmarks named here are looked up automatically.">
              {(p) => <Input {...p} className="input script" maxLength={512} value={form.location_text} onChange={(e) => set('location_text', e.target.value)} />}
            </Field>
            <div className="row-wrap">
              <Button icon={<MapPin size={14} />} onClick={() => setPicking(true)}>{form.position ? 'Change position' : 'Set exact position'}</Button>
              {form.position && (
                <>
                  <span className="small num">{formatCoordinates(form.position.latitude, form.position.longitude)}</span>
                  <Button size="sm" variant="ghost" onClick={() => set('position', null)}>Remove</Button>
                </>
              )}
              <span className="xs faint">Only if you know it. It will be recorded as confirmed by you.</span>
            </div>
          </div>
        </Panel>
        {error?.message && (
          <Callout tone="bad" title={error.network ? 'Not sent' : 'Not saved'}>
            {error.message}{error.network && ' Your text is kept. Submit again when the connection returns; it will not be recorded twice.'}
          </Callout>
        )}
        <div className="row">
          <Button type="submit" variant="primary" busy={create.isPending} disabled={closed}>Record report</Button>
          <Button onClick={() => setForm(EMPTY)} disabled={create.isPending}>Clear</Button>
        </div>
      </form>
      <Dialog open={picking} wide title="Set exact position" onClose={() => setPicking(false)}
        footer={<Button variant="primary" onClick={() => setPicking(false)}>Done</Button>}>
        <div style={{ height: 380 }}>
          <LazyMap incidents={[]} center={form.position ?? operation!.map_center} picking onPick={(p) => set('position', p)} label="Pick the reported position" legendOpen={false} />
        </div>
        <span className="small">{form.position ? <>Selected <span className="num">{formatCoordinates(form.position.latitude, form.position.longitude)}</span></> : 'Click the map.'}</span>
      </Dialog>
    </div>
  );
}

export function IntakePage() {
  return <RequireOperation><Form /></RequireOperation>;
}
