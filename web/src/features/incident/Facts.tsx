import { Pencil } from 'lucide-react';
import { useState } from 'react';

import { Button, Callout, Dialog, Field, Input, ProvenanceTag, Select, Textarea, useToast } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { humanize } from '../../lib/format';
import { CATEGORIES, extractorLabel, FACT, PRIORITY, PRIORITY_ORDER } from '../../lib/labels';
import { mutations } from '../../lib/queries';
import type { Fact, IncidentDetail } from '../../lib/types';
import { SectionHeading } from './SectionHeading';

export function factValue(fact: Fact): string | null {
  const value = fact.value;
  if (value === null || value === undefined) return null;
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.length ? value.map((v) => humanize(String(v))).join(', ') : null;
  if (fact.name === 'water_depth_cm' && typeof value === 'number') return `${Math.round(value)} cm`;
  if (fact.name === 'category') return humanize(String(value));
  return String(value);
}

function FactRow({ fact }: { fact: Fact }) {
  const [open, setOpen] = useState(false);
  const shown = factValue(fact);
  const source = fact.sources[0];
  return (
    <div className="fact-row" data-known={shown !== null} data-origin={fact.origin}>
      <span className="fact-label">
        <span>{FACT[fact.name] ?? humanize(fact.name)}</span>
        {fact.origin === 'operator' && <span className="badge tag-human" title="Corrected by an operator">Operator</span>}
        {fact.origin === 'extracted' && source && (
          <button type="button" className="badge tag-machine" style={{ border: 0, cursor: 'pointer' }} onClick={() => setOpen((v) => !v)} aria-expanded={open}
            title="Show the words this was extracted from">
            {extractorLabel(source.extractor)}
          </button>
        )}
      </span>
      {shown === null ? (
        <span className="unknown small">Not reported</span>
      ) : (
        <span className={`fact-value${fact.origin === 'extracted' ? ' machine-value' : ''}`}>{shown}</span>
      )}
      {open && fact.sources.length > 0 && (
        <ul className="fact-sources small">
          {fact.sources.map((s, i) => (
            <li key={i} className="stack-sm" style={{ gap: 2 }}>
              <span className="row-wrap"><ProvenanceTag extractor={s.extractor} model={s.model} /><span className="muted">found {humanize(String(s.value))}</span></span>
              {s.quote && <span className="quote script">“{s.quote}”</span>}
              {s.note && <span className="faint xs">{s.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function FactsSection({ incident }: { incident: IncidentDetail }) {
  const { can } = useAuth();
  const [editing, setEditing] = useState(false);
  const shown = incident.facts.filter((f) => f.name !== 'summary');
  const machine = incident.facts.some((f) => f.origin === 'extracted');
  return (
    <section className="detail-section" aria-labelledby="facts-h">
      <div className="spread">
        <SectionHeading id="facts-h">Situation</SectionHeading>
        {can('incidents:update') && incident.status !== 'duplicate' && incident.status !== 'closed' && (
          <Button size="sm" icon={<Pencil size={13} />} onClick={() => setEditing(true)}>Correct</Button>
        )}
      </div>
      {incident.summary && <p>{incident.summary}</p>}
      {machine && (
        <p className="xs faint">
          Underlined values were extracted automatically and are not yet confirmed by a person. Select a tag to see the words they came from.
        </p>
      )}
      <div className="fact-grid">{shown.map((fact) => <FactRow key={fact.name} fact={fact} />)}</div>
      {incident.priority_reasons.length > 0 && (
        <div className="stack-sm">
          <span className="small muted">Why this priority ({incident.priority_source === 'operator' ? 'set by an operator' : 'triage rules'})</span>
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {incident.priority_reasons.map((r) => <li key={r}>{humanize(r)}</li>)}
          </ul>
        </div>
      )}
      {editing && <CorrectionDialog incident={incident} onClose={() => setEditing(false)} />}
    </section>
  );
}

type Tri = '' | 'true' | 'false' | 'unknown';

function triFrom(value: unknown): Tri {
  return value === true ? 'true' : value === false ? 'false' : '';
}

function CorrectionDialog({ incident, onClose }: { incident: IncidentDetail; onClose: () => void }) {
  const toast = useToast();
  const correct = mutations.useCorrect(incident.id);
  const fact = (name: string) => incident.facts.find((f) => f.name === name)?.value;
  const [people, setPeople] = useState(fact('people_count') != null ? String(fact('people_count')) : '');
  const [trapped, setTrapped] = useState<Tri>(triFrom(fact('trapped_status')));
  const [medical, setMedical] = useState<Tri>(triFrom(fact('medical_emergency')));
  const [vulnerable, setVulnerable] = useState<Tri>(triFrom(fact('vulnerable_present')));
  const [trend, setTrend] = useState(String(fact('water_level_trend') ?? ''));
  const [category, setCategory] = useState(incident.category);
  const [summary, setSummary] = useState(incident.summary ?? '');
  const [locationText, setLocationText] = useState(incident.location.description ?? '');
  const [priority, setPriority] = useState('');
  const [note, setNote] = useState('');

  const submit = async () => {
    const facts: Record<string, unknown> = {};
    const original = (name: string) => fact(name) ?? null;
    const triValue = (t: Tri) => (t === 'true' ? true : t === 'false' ? false : null);
    const peopleValue = people.trim() === '' ? null : Number(people);
    if (peopleValue !== original('people_count')) facts.people_count = peopleValue;
    for (const [name, value] of [['trapped_status', trapped], ['medical_emergency', medical], ['vulnerable_present', vulnerable]] as const) {
      if (triValue(value) !== original(name)) facts[name] = triValue(value);
    }
    if ((trend || null) !== original('water_level_trend')) facts.water_level_trend = trend || null;
    const body: Record<string, unknown> = { note: note.trim() || undefined };
    if (Object.keys(facts).length) body.facts = facts;
    if (category !== incident.category) body.category = category;
    if (summary !== (incident.summary ?? '')) body.summary = summary;
    if (locationText !== (incident.location.description ?? '')) body.location_description = locationText;
    if (priority === 'policy') body.clear_priority_override = true;
    else if (priority) body.priority = priority;
    try {
      await correct.mutateAsync(body);
      toast('success', `${incident.reference} updated`);
      onClose();
    } catch (error) {
      toast('error', errorMessage(error));
    }
  };

  const triSelect = (value: Tri, set: (v: Tri) => void) => (props: object) => (
    <Select {...props} value={value} onChange={(e) => set(e.target.value as Tri)}>
      <option value="">Unknown</option>
      <option value="true">Yes</option>
      <option value="false">No (confirmed)</option>
    </Select>
  );

  return (
    <Dialog
      open
      wide
      title={`Correct ${incident.reference}`}
      description="Corrections are recorded under your name. Extracted values and the original report are kept."
      onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={correct.isPending} onClick={submit}>Save corrections</Button></>}
    >
      <div className="form-grid">
        <Field label="People at location">{(p) => <Input {...p} type="number" min={0} inputMode="numeric" value={people} onChange={(e) => setPeople(e.target.value)} />}</Field>
        <Field label="People trapped">{triSelect(trapped, setTrapped)}</Field>
        <Field label="Medical need">{triSelect(medical, setMedical)}</Field>
        <Field label="Vulnerable people">{triSelect(vulnerable, setVulnerable)}</Field>
        <Field label="Water level">
          {(p) => (
            <Select {...p} value={trend} onChange={(e) => setTrend(e.target.value)}>
              <option value="">Unknown</option><option value="rising">Rising</option><option value="stable">Stable</option>
              <option value="falling">Falling</option><option value="receded">Receded</option>
            </Select>
          )}
        </Field>
        <Field label="Category">
          {(p) => <Select {...p} value={category} onChange={(e) => setCategory(e.target.value)}>{CATEGORIES.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}</Select>}
        </Field>
      </div>
      <Field label="Summary">{(p) => <Input {...p} maxLength={500} value={summary} onChange={(e) => setSummary(e.target.value)} />}</Field>
      <Field label="Location description" hint="How the caller describes the place. Setting coordinates is done in the Location section.">
        {(p) => <Input {...p} maxLength={512} value={locationText} onChange={(e) => setLocationText(e.target.value)} />}
      </Field>
      <Field label="Priority" hint="Leave as is to use the triage rules. Setting it by hand requires a note.">
        {(p) => (
          <Select {...p} value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">No change ({PRIORITY[incident.priority].label}{incident.priority_source === 'operator' ? ', set by operator' : ''})</option>
            {PRIORITY_ORDER.filter((x) => x !== 'unassessed').map((x) => <option key={x} value={x}>{PRIORITY[x].label}</option>)}
            {incident.priority_source === 'operator' && <option value="policy">Return to triage rules</option>}
          </Select>
        )}
      </Field>
      <Field label="Note" hint="Why the change was made, e.g. what the caller said on callback.">
        {(p) => <Textarea {...p} rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />}
      </Field>
      {priority && priority !== 'policy' && !note.trim() && <Callout tone="warn">A note is required when setting priority by hand.</Callout>}
    </Dialog>
  );
}
