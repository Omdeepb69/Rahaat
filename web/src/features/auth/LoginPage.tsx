import { ArrowLeft, Building2, MapPinned, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { Logo } from '../../components/Shell';
import { Button, Callout, Field, Input, Select } from '../../components/ui';
import { ApiError, errorMessage, NetworkError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { config } from '../../lib/config';
import { findState, rememberedPlace, rememberPlace, useJurisdictions } from '../../lib/jurisdictions';
import { useConnection } from '../../lib/live';

const NATIONAL = 'national';

export function LoginPage() {
  const { login, expiredNotice } = useAuth();
  const connection = useConnection();
  const directory = useJurisdictions();
  const remembered = useMemo(() => rememberedPlace('control'), []);
  const [stateCode, setStateCode] = useState(remembered?.state ?? '');
  const [districtCode, setDistrictCode] = useState(remembered?.district ?? '');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const state = findState(directory.data, stateCode);
  const district = state?.districts.find((d) => d.code === districtCode);
  const national = stateCode === NATIONAL;

  useEffect(() => {
    if (directory.data && stateCode && !national && !state) {
      setStateCode('');
      setDistrictCode('');
    }
  }, [directory.data, stateCode, national, state]);

  const target = national
    ? 'National administration'
    : district
      ? `${district.name} district control room`
      : state
        ? `${state.name} state control room`
        : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!stateCode) { setError('Choose your state or union territory.'); return; }
    if (!password) { setError('Enter the password for this control room.'); return; }
    setBusy(true);
    setError(null);
    try {
      await login({
        level: national ? 'national' : districtCode ? 'district' : 'state',
        state_code: national ? null : stateCode,
        district_code: national ? null : districtCode || null,
        password,
      });
      rememberPlace('control', { state: stateCode, district: districtCode });
    } catch (e) {
      if (e instanceof ApiError && e.status === 423) setError('This control room account is locked for a few minutes after repeated failed attempts.');
      else if (e instanceof ApiError && e.status === 429) setError('Too many attempts from this device. Wait a minute and try again.');
      else if (e instanceof ApiError && e.status === 401) setError(`Incorrect password for the ${target ?? 'selected'} account, or that account has not been issued yet.`);
      else if (e instanceof NetworkError) setError(`The RAAHAT server at ${new URL(config.apiBaseUrl).host} cannot be reached.`);
      else setError(errorMessage(e));
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  const states = directory.data?.states.filter((s) => s.kind === 'state') ?? [];
  const territories = directory.data?.states.filter((s) => s.kind === 'union_territory') ?? [];

  return (
    <div className="auth">
      <aside className="auth-aside" aria-label="About RAAHAT">
        <Link to="/" className="brand auth-enter" style={{ ['--i' as string]: 0 }}><Logo size={28} /> RAAHAT</Link>
        <div>
          <p className="auth-claim auth-enter" style={{ ['--i' as string]: 1 }}>Every district sees its own calls, the moment they arrive.</p>
          <ul className="auth-points">
            <li className="auth-enter" style={{ ['--i' as string]: 2 }}><MapPinned size={18} aria-hidden />Reports from the public are routed by state and district. A control room sees only its own area.</li>
            <li className="auth-enter" style={{ ['--i' as string]: 3 }}><Building2 size={18} aria-hidden />State control rooms oversee all of their districts. The national administration issues accounts.</li>
            <li className="auth-enter" style={{ ['--i' as string]: 4 }}><ShieldCheck size={18} aria-hidden />Every change is recorded. A person approves every dispatch.</li>
          </ul>
        </div>
        <p className="auth-foot">For authorised control room staff. Members of the public: <Link to="/report">report an emergency here</Link>, or call 112.</p>
      </aside>
      <main className="auth-main">
        <form className="auth-card" onSubmit={submit} noValidate aria-describedby="login-intro">
          <Link to="/" className="small row back-link"><ArrowLeft size={14} aria-hidden /> Public site</Link>
          <div className="stack-sm">
            <h1>Authority sign-in</h1>
            <p id="login-intro" className="muted small">Choose your control room, then enter the password issued to it.</p>
          </div>
          {expiredNotice && <Callout>Your session ended. Sign in again to continue.</Callout>}
          {connection.backend === 'offline' && <Callout tone="bad">The server cannot be reached. Sign-in will fail until it is back.</Callout>}
          {directory.isError && <Callout tone="bad">The list of states could not be loaded. {errorMessage(directory.error)}</Callout>}
          <Field label="State or union territory">
            {(p) => (
              <Select
                {...p}
                name="state"
                required
                value={stateCode}
                disabled={directory.isPending}
                onChange={(e) => { setStateCode(e.target.value); setDistrictCode(''); setError(null); }}
                autoFocus={!stateCode}
              >
                <option value="" disabled>{directory.isPending ? 'Loading…' : 'Choose…'}</option>
                <option value={NATIONAL}>National administration</option>
                <optgroup label="States">{states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}</optgroup>
                <optgroup label="Union territories">{territories.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}</optgroup>
              </Select>
            )}
          </Field>
          {!national && (
            <Field label="District" hint={state ? `${state.districts.length} districts. Leave on the state control room to oversee all of them.` : 'Choose a state first.'}>
              {(p) => (
                <Select {...p} name="district" value={districtCode} disabled={!state} onChange={(e) => { setDistrictCode(e.target.value); setError(null); }}>
                  <option value="">{state ? `${state.name} state control room` : '—'}</option>
                  {state?.districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
                </Select>
              )}
            </Field>
          )}
          <Field label="Password">
            {(p) => (
              <Input
                {...p}
                name="password"
                type="password"
                autoComplete="current-password"
                enterKeyHint="go"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus={!!stateCode}
              />
            )}
          </Field>
          {error && <Callout tone="bad">{error}</Callout>}
          <Button type="submit" variant="primary" busy={busy}>{target ? `Sign in to ${target}` : 'Sign in'}</Button>
        </form>
      </main>
    </div>
  );
}

export function ChangePasswordPage() {
  const { changePassword, logout, user } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (next.length < 12) { setError('The new password must be at least 12 characters.'); return; }
    if (next !== repeat) { setError('The new passwords do not match.'); return; }
    setBusy(true);
    setError(null);
    try { await changePassword(current, next); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  return (
    <main className="auth-single">
      <div className="panel" style={{ inlineSize: 'min(26rem, 100%)' }}>
        <div className="panel-header"><span className="brand"><Logo /> RAAHAT</span></div>
        <form className="panel-body stack" onSubmit={submit} noValidate>
          <h1>Choose a new password</h1>
          <p className="small muted">{user?.jurisdiction.label ?? user?.full_name}: the password you signed in with was temporary. Replace it to continue.</p>
          <Field label="Temporary password">{(p) => <Input {...p} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus />}</Field>
          <Field label="New password" hint="At least 12 characters. A phrase of several words works well.">{(p) => <Input {...p} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />}</Field>
          <Field label="Repeat new password">{(p) => <Input {...p} type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} />}</Field>
          {error && <Callout tone="bad">{error}</Callout>}
          <div className="row"><Button type="submit" variant="primary" busy={busy}>Set password</Button><Button variant="ghost" onClick={logout}>Sign out</Button></div>
        </form>
      </div>
    </main>
  );
}
