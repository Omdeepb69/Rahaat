import { Field, Select } from './ui';
import { findState, useJurisdictions } from '../lib/jurisdictions';

export interface Picked { state: string; district: string }

/**
 * State then district. ``fixedState`` locks the state (a state control room);
 * ``allowStateWide`` offers the whole state as the first district choice.
 */
export function JurisdictionPicker({
  value, onChange, fixedState, allowStateWide = true, stateWideLabel = 'Whole state',
}: {
  value: Picked;
  onChange: (next: Picked) => void;
  fixedState?: string | null;
  allowStateWide?: boolean;
  stateWideLabel?: string;
}) {
  const directory = useJurisdictions();
  const stateCode = fixedState ?? value.state;
  const state = findState(directory.data, stateCode);
  return (
    <div className="form-grid">
      <Field label="State or union territory">
        {(p) => (
          <Select {...p} value={stateCode} disabled={!!fixedState || directory.isPending} onChange={(e) => onChange({ state: e.target.value, district: '' })}>
            <option value="" disabled>{directory.isPending ? 'Loading…' : 'Choose…'}</option>
            {directory.data?.states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
          </Select>
        )}
      </Field>
      <Field label="District">
        {(p) => (
          <Select {...p} value={value.district} disabled={!state} onChange={(e) => onChange({ state: stateCode, district: e.target.value })}>
            {allowStateWide ? <option value="">{stateWideLabel}</option> : <option value="" disabled>Choose…</option>}
            {state?.districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </Select>
        )}
      </Field>
    </div>
  );
}
