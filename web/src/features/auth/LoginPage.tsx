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
    <main className="auth">
      <div className="panel auth-card">
        <div className="panel-header"><span className="brand"><Logo /> RAAHAT</span><span className="xs muted">Emergency coordination</span></div>
        <form className="panel-body" onSubmit={submit}>
          <h1>Sign in</h1>
          {expiredNotice && <Callout>Your session ended. Sign in again to continue.</Callout>}
          {connection.backend === 'offline' && <Callout tone="bad">The server cannot be reached. Sign-in will fail until it is back.</Callout>}
          <Field label="Username">{(p) => <Input {...p} autoComplete="username" autoCapitalize="none" spellCheck={false} required value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />}</Field>
          <Field label="Password">{(p) => <Input {...p} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
          {error && <Callout tone="bad">{error}</Callout>}
          <Button type="submit" variant="primary" busy={busy}>Sign in</Button>
          <p className="xs faint">Accounts are issued by your administrator. RAAHAT is a decision-support tool; it does not contact emergency services.</p>
        </form>
      </div>
    </main>
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
    <main className="auth">
      <div className="panel auth-card">
        <div className="panel-header"><span className="brand"><Logo /> RAAHAT</span></div>
        <form className="panel-body" onSubmit={submit}>
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
