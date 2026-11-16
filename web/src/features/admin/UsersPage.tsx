import { KeyRound, Plus } from 'lucide-react';
import { Fragment, useState } from 'react';

import { Badge, Button, Callout, Dialog, ErrorState, Field, Input, SkeletonList, PageHeader, Panel, Select, TimeAgo, useToast } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { ROLE } from '../../lib/labels';
import { mutations, useUsers } from '../../lib/queries';
import type { Role, UserAccount } from '../../lib/types';

const ROLES = Object.keys(ROLE) as Role[];

function CreateUser({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const create = mutations.useCreateUser();
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [role, setRole] = useState<Role>('operator');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog open title="Create user" onClose={onClose} description="The user must replace this temporary password when they first sign in. Share it through a separate channel."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={create.isPending} onClick={async () => {
        try { await create.mutateAsync({ username, full_name: fullName, role, initial_password: password }); toast('success', `User ${username} created`); onClose(); } catch (e) { setError(errorMessage(e)); }
      }}>Create</Button></>}>
      <Field label="Username" required hint="Lowercase letters, digits, dot, dash, underscore">{(p) => <Input {...p} autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value.toLowerCase())} />}</Field>
      <Field label="Full name" required>{(p) => <Input {...p} value={fullName} onChange={(e) => setFullName(e.target.value)} />}</Field>
      <Field label="Role" hint={ROLE[role].description}>{(p) => <Select {...p} value={role} onChange={(e) => setRole(e.target.value as Role)}>{ROLES.map((r) => <option key={r} value={r}>{ROLE[r].label}</option>)}</Select>}</Field>
      <Field label="Temporary password" required hint="At least 12 characters.">{(p) => <Input {...p} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
      {error && <Callout tone="bad">{error}</Callout>}
    </Dialog>
  );
}

function EditUser({ user, onClose }: { user: UserAccount; onClose: () => void }) {
  const toast = useToast();
  const { user: me } = useAuth();
  const update = mutations.useUpdateUser();
  const reset = mutations.useResetPassword();
  const [role, setRole] = useState<Role>(user.role);
  const [active, setActive] = useState(user.is_active);
  const [password, setPassword] = useState('');
  const self = me?.id === user.id;
  const save = async () => {
    try {
      if (role !== user.role || active !== user.is_active) await update.mutateAsync({ id: user.id, role, is_active: active });
      if (password) await reset.mutateAsync({ id: user.id, new_password: password });
      toast('success', `${user.username} updated`);
      onClose();
    } catch (e) {
      toast('error', errorMessage(e));
    }
  };
  return (
    <Dialog open title={`Edit ${user.username}`} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={update.isPending || reset.isPending} onClick={save}>Save</Button></>}>
      <Field label="Role" hint={ROLE[role].description}>{(p) => <Select {...p} disabled={self} value={role} onChange={(e) => setRole(e.target.value as Role)}>{ROLES.map((r) => <option key={r} value={r}>{ROLE[r].label}</option>)}</Select>}</Field>
      <label className="checkbox"><input type="checkbox" disabled={self} checked={active} onChange={(e) => setActive(e.target.checked)} />Account active</label>
      {self && <span className="small muted">You cannot change your own role or deactivate yourself.</span>}
      <Field label="Set temporary password" hint="Ends the user's current sessions and clears any lockout. They must change it at next sign-in.">
        {(p) => <Input {...p} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
      </Field>
    </Dialog>
  );
}

export function UsersPage() {
  const users = useUsers(true);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<UserAccount | null>(null);
  return (
    <div className="page">
      <PageHeader title="Users" description="Accounts and roles. Permissions are enforced by the server." actions={<Button variant="primary" icon={<Plus size={14} />} onClick={() => setCreating(true)}>Create user</Button>} />
      <Panel flush>
        {users.isLoading && <SkeletonList rows={6} />}
        {users.isError && <ErrorState error={users.error} />}
        {users.data && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>User</th><th>Role</th><th>State</th><th>Last sign-in</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {users.data.map((u) => (
                  <tr key={u.id}>
                    <td><strong>{u.full_name}</strong><div className="xs muted">{u.username}</div></td>
                    <td>{ROLE[u.role].label}</td>
                    <td className="row-wrap">
                      <Badge tone={u.is_active ? 'tone-ok' : 'tone-idle'}>{u.is_active ? 'Active' : 'Deactivated'}</Badge>
                      {u.must_change_password && <Badge tone="tone-warn"><KeyRound size={11} aria-hidden />Password change pending</Badge>}
                      {u.locked_until && Date.parse(u.locked_until) > Date.now() && <Badge tone="tone-bad">Locked</Badge>}
                    </td>
                    <td className="small">{u.last_login_at ? <TimeAgo value={u.last_login_at} /> : 'Never'}</td>
                    <td><Button size="sm" onClick={() => setEditing(u)}>Edit</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel title="Roles">
        <dl className="kv">{ROLES.map((r) => <Fragment key={r}><dt>{ROLE[r].label}</dt><dd>{ROLE[r].description}</dd></Fragment>)}</dl>
      </Panel>
      {creating && <CreateUser onClose={() => setCreating(false)} />}
      {editing && <EditUser user={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
