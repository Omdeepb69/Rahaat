import { Check, Copy, KeyRound } from 'lucide-react';
import { useState } from 'react';

import { JurisdictionPicker, type Picked } from '../../components/JurisdictionPicker';
import { Badge, Button, Callout, Dialog, ErrorState, Field, PageHeader, Panel, Select, SkeletonList, TimeAgo, useToast } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { ROLE } from '../../lib/labels';
import { mutations, useUsers } from '../../lib/queries';
import type { IssuedPassword, JurisdictionLevel, UserAccount } from '../../lib/types';

function levelOf(u: UserAccount): JurisdictionLevel {
  if (!u.state_code) return 'national';
  return u.district_code ? 'district' : 'state';
}

function Issued({ issued, onClose }: { issued: IssuedPassword; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(issued.password);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <Dialog open title={issued.created ? 'Account created' : 'New password issued'} onClose={onClose}
      description={issued.user.jurisdiction}
      footer={<Button variant="primary" onClick={onClose}>I have recorded it</Button>}>
      <Callout tone="warn" title="Shown only once">
        Give this password to the control room through a separate, trusted channel. It is stored only in scrambled form and cannot be shown again.
        {!issued.created && ' The previous password has stopped working and anyone signed in with it has been signed out.'}
      </Callout>
      <div className="row" style={{ gap: 'var(--s-3)' }}>
        <code className="mono" style={{ fontSize: '1.25rem', padding: 'var(--s-3) var(--s-4)', background: 'var(--surface-sunken)', borderRadius: 'var(--radius-sm)' }}>{issued.password}</code>
        <Button icon={copied ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />} onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>
      </div>
      <p className="small muted">To sign in: choose {issued.user.jurisdiction.replace(/ control room.*$/, '')} on the sign-in page, then enter this password.</p>
    </Dialog>
  );
}

function IssuePanel({ onIssued }: { onIssued: (issued: IssuedPassword) => void }) {
  const issue = mutations.useIssuePassword();
  const [level, setLevel] = useState<JurisdictionLevel>('district');
  const [place, setPlace] = useState<Picked>({ state: '', district: '' });
  const [error, setError] = useState<string | null>(null);
  const ready = level === 'national' || (place.state && (level === 'state' || place.district));
  const submit = async () => {
    setError(null);
    try {
      onIssued(await issue.mutateAsync({
        level,
        state_code: level === 'national' ? null : place.state,
        district_code: level === 'district' ? place.district : null,
      }));
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  return (
    <Panel title="Issue a control room password">
      <div className="stack">
        <p className="small muted">Creates the account if it does not exist yet. Issuing again replaces the password.</p>
        <Field label="Level">
          {(p) => (
            <Select {...p} value={level} onChange={(e) => setLevel(e.target.value as JurisdictionLevel)}>
              <option value="district">District control room</option>
              <option value="state">State control room</option>
              <option value="national">National administration</option>
            </Select>
          )}
        </Field>
        {level !== 'national' && (
          <JurisdictionPicker value={place} onChange={setPlace} allowStateWide={level === 'state'} stateWideLabel="Not needed for a state account" />
        )}
        {error && <Callout tone="bad">{error}</Callout>}
        <div><Button variant="primary" icon={<KeyRound size={15} aria-hidden />} disabled={!ready} busy={issue.isPending} onClick={submit}>Issue password</Button></div>
      </div>
    </Panel>
  );
}

function Reissue({ user, onIssued }: { user: UserAccount; onIssued: (issued: IssuedPassword) => void }) {
  const toast = useToast();
  const issue = mutations.useIssuePassword();
  const [confirm, setConfirm] = useState(false);
  return (
    <>
      <Button size="sm" onClick={() => setConfirm(true)}>New password</Button>
      <Dialog open={confirm} title={`Replace the password for ${user.jurisdiction}?`} onClose={() => setConfirm(false)}
        description="Everyone signed in to this control room will be signed out and must use the new password."
        footer={<><Button onClick={() => setConfirm(false)}>Cancel</Button><Button variant="primary" busy={issue.isPending} onClick={async () => {
          try {
            const issued = await issue.mutateAsync({ level: levelOf(user), state_code: user.state_code, district_code: user.district_code });
            setConfirm(false);
            onIssued(issued);
          } catch (e) { toast('error', errorMessage(e)); }
        }}>Replace password</Button></>}>
        <p className="small muted">The new password is shown once, on the next screen.</p>
      </Dialog>
    </>
  );
}

function ActiveToggle({ user }: { user: UserAccount }) {
  const toast = useToast();
  const { user: me } = useAuth();
  const update = mutations.useUpdateUser();
  if (me?.id === user.id) return null;
  return (
    <Button size="sm" variant="ghost" busy={update.isPending} onClick={async () => {
      try { await update.mutateAsync({ id: user.id, is_active: !user.is_active }); toast('success', user.is_active ? 'Account suspended' : 'Account restored'); } catch (e) { toast('error', errorMessage(e)); }
    }}>{user.is_active ? 'Suspend' : 'Restore'}</Button>
  );
}

export function UsersPage() {
  const users = useUsers(true);
  const [issued, setIssued] = useState<IssuedPassword | null>(null);
  const accounts = [...(users.data ?? [])].sort((a, b) => levelOf(a).localeCompare(levelOf(b)) || a.jurisdiction.localeCompare(b.jurisdiction));
  return (
    <div className="page">
      <PageHeader title="Control room accounts" description="One account per control room. Each sees only the reports and operations of its own state or district; the server enforces this." />
      <IssuePanel onIssued={setIssued} />
      <Panel flush title={`Accounts${users.data ? ` (${users.data.length})` : ''}`}>
        {users.isLoading && <SkeletonList rows={6} />}
        {users.isError && <ErrorState error={users.error} />}
        {users.data && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Control room</th><th>Access</th><th>Status</th><th>Last sign-in</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {accounts.map((u) => (
                  <tr key={u.id}>
                    <td><strong>{u.jurisdiction}</strong><div className="xs muted mono">{u.username}</div></td>
                    <td className="small">{ROLE[u.role].label}</td>
                    <td className="row-wrap">
                      <Badge tone={u.is_active ? 'tone-ok' : 'tone-idle'}>{u.is_active ? 'Active' : 'Suspended'}</Badge>
                      {u.locked_until && Date.parse(u.locked_until) > Date.now() && <Badge tone="tone-bad">Locked</Badge>}
                    </td>
                    <td className="small">{u.last_login_at ? <TimeAgo value={u.last_login_at} /> : 'Never'}</td>
                    <td><div className="row">{u.state_code || u.username === 'national' ? <Reissue user={u} onIssued={setIssued} /> : null}<ActiveToggle user={u} /></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {issued && <Issued issued={issued} onClose={() => setIssued(null)} />}
    </div>
  );
}
