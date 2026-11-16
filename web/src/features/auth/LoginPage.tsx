import { FileCheck2, Languages, ShieldCheck } from 'lucide-react';
import { useState, type FormEvent } from 'react';

import { Logo } from '../../components/Shell';
import { Button, Callout, Field, Input } from '../../components/ui';
import { ApiError, errorMessage, NetworkError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { config } from '../../lib/config';
import { useConnection } from '../../lib/live';

export function LoginPage() {
  const { login, expiredNotice } = useAuth();
  const connection = useConnection();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError('Enter your username and password.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (e) {
      if (e instanceof ApiError && e.status === 423) setError('This account is temporarily locked after repeated failed attempts. Try again later or ask an administrator.');
      else if (e instanceof ApiError && e.status === 429) setError('Too many attempts from this device. Wait a minute and try again.');
      else if (e instanceof NetworkError) setError(`The RAAHAT server at ${new URL(config.apiBaseUrl).host} cannot be reached.`);
      else setError(errorMessage(e));
      setPassword('');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="auth">
      <aside className="auth-aside" aria-label="About RAAHAT">
        <span className="brand auth-enter" style={{ ['--i' as string]: 0 }}><Logo size={28} /> RAAHAT</span>
        <div>
          <p className="auth-claim auth-enter" style={{ ['--i' as string]: 1 }}>Coordinate disaster response from the first call to the rescue.</p>
          <ul className="auth-points">
            <li className="auth-enter" style={{ ['--i' as string]: 2 }}><Languages size={18} aria-hidden />Reports in Malayalam, English, Hindi and Konkani, kept in the caller's own words.</li>
            <li className="auth-enter" style={{ ['--i' as string]: 3 }}><FileCheck2 size={18} aria-hidden />Every fact and position shows where it came from. Nothing is guessed.</li>
            <li className="auth-enter" style={{ ['--i' as string]: 4 }}><ShieldCheck size={18} aria-hidden />Recommendations explain themselves. A person approves every dispatch.</li>
          </ul>
        </div>
        <p className="auth-foot">For authorised control-room staff. RAAHAT supports decisions; it does not contact emergency services. In an emergency, call 112.</p>
      </aside>
      <main className="auth-main">
        <form className="auth-card" onSubmit={submit} noValidate>
          <div className="stack-sm">
            <h1>Sign in</h1>
            <p className="muted small">Use the account your administrator issued.</p>
          </div>
          {expiredNotice && <Callout>Your session ended. Sign in again to continue.</Callout>}
          {connection.backend === 'offline' && <Callout tone="bad">The server cannot be reached. Sign-in will fail until it is back.</Callout>}
          <Field label="Username">{(p) => <Input {...p} name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} enterKeyHint="next" required value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />}</Field>
          <Field label="Password">{(p) => <Input {...p} name="password" type="password" autoComplete="current-password" enterKeyHint="go" required value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
          {error && <Callout tone="bad">{error}</Callout>}
          <Button type="submit" variant="primary" busy={busy}>Sign in</Button>
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
          <p className="small muted">{user?.full_name}, your administrator issued a temporary password. Replace it to continue.</p>
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
