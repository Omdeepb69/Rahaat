import {
  Activity, ClipboardList, Megaphone, FileText, LayoutDashboard, LogOut, Menu, PlusCircle, Radio, ServerCog, Settings, Truck, Users,
} from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { useAuth } from '../lib/auth';
import { formatAge, formatTime } from '../lib/format';
import { ROLE } from '../lib/labels';
import { useConnection, useNow, useStream } from '../lib/live';
import { useOperation } from '../lib/operation';
import { useIncidentCounts } from '../lib/queries';
import type { Permission } from '../lib/types';
import { Button, Select } from './ui';

export function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="6" fill="currentColor" />
      <path d="M8 22V10h7.5a4 4 0 0 1 0 8H12m3.5 0L22 22" fill="none" stroke="var(--bg)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="23.5" cy="10" r="2.5" fill="#d9480f" />
    </svg>
  );
}

/** Live status shown in the header. Never says "live" unless the stream is actually open and recent. */
function ConnectionIndicator() {
  const connection = useConnection();
  const stream = useStream();
  useNow(5_000);
  let tone = 'tone-outline';
  let text = 'Connecting';
  let title = 'Contacting the RAAHAT server';
  if (connection.backend === 'offline') {
    tone = 'tone-bad';
    text = 'Server unreachable';
    title = connection.detail ?? '';
  } else if (connection.backend === 'degraded') {
    tone = 'tone-warn';
    text = 'Server degraded';
    title = connection.detail ?? '';
  } else if (stream.state === 'live') {
    tone = 'tone-ok';
    text = 'Live';
    title = stream.lastMessageAt ? `Last update from the server ${formatAge(stream.lastMessageAt)} ago` : 'Receiving updates';
  } else if (stream.state === 'reconnecting') {
    tone = 'tone-warn';
    text = 'Reconnecting';
    title = 'Live updates interrupted. Missed changes will be replayed on reconnect.';
  }
  return (
    <span className={`badge ${tone}`} role="status" aria-live="polite" title={title}>
      <span className="dot" aria-hidden />
      {text}
    </span>
  );
}

function OfflineBanner() {
  const connection = useConnection();
  const now = useNow(5_000);
  if (connection.backend !== 'offline' && connection.backend !== 'degraded') return null;
  const since = connection.offlineSince;
  return (
    <div className={`banner ${connection.backend === 'offline' ? 'banner-bad' : 'banner-warn'}`} role="alert">
      <strong>{connection.backend === 'offline' ? 'The RAAHAT server cannot be reached.' : 'The RAAHAT server is not healthy.'}</strong>
      <span>
        {connection.lastContactAt
          ? <>Information on screen was last confirmed at <time className="num">{formatTime(connection.lastContactAt)}</time> ({formatAge(connection.lastContactAt, now)} ago) and may be out of date.</>
          : 'No information has been loaded.'}
        {since && connection.backend === 'offline' && <> Unreachable for {formatAge(since, now)}.</>} Changes cannot be saved until the connection returns.
      </span>
    </div>
  );
}

function OperationSelect() {
  const { operation, operations, select } = useOperation();
  if (!operations.length) return <span className="muted small hide-narrow">No operation open</span>;
  return (
    <div className="row" style={{ minWidth: 0 }}>
      <label htmlFor="operation-select" className="sr-only">Operation</label>
      <Select id="operation-select" value={operation?.id ?? ''} onChange={(e) => select(e.target.value)} style={{ maxWidth: 280 }}>
        {operations.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}{o.status === 'closed' ? ' (closed)' : ''}
          </option>
        ))}
      </Select>
    </div>
  );
}

interface NavItem { to: string; label: string; icon: ReactNode; permission?: Permission; count?: number | null; end?: boolean }

export function Shell({ children }: { children: ReactNode }) {
  const { user, logout, can } = useAuth();
  const { operation } = useOperation();
  const counts = useIncidentCounts(operation?.id ?? null);
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);

  const review = counts.data ? (counts.data.by_status.unverified ?? 0) + (counts.data.by_status.under_review ?? 0) : null;
  const items: { section: string; links: NavItem[] }[] = [
    {
      section: 'Operations',
      links: [
        { to: '/', label: 'Operations board', icon: <LayoutDashboard size={16} />, permission: 'incidents:read', end: true },
        { to: '/intake', label: 'New report', icon: <PlusCircle size={16} />, permission: 'reports:create' },
        { to: '/incidents', label: 'Incidents', icon: <ClipboardList size={16} />, permission: 'incidents:read', count: review },
        { to: '/reports', label: 'Reports', icon: <FileText size={16} />, permission: 'reports:read' },
        { to: '/dispatch', label: 'Dispatch', icon: <Radio size={16} />, permission: 'dispatch:read' },
        { to: '/resources', label: 'Resources', icon: <Truck size={16} />, permission: 'resources:read' },
        { to: '/alerts', label: 'Official alerts', icon: <Megaphone size={16} />, permission: 'incidents:read' },
      ],
    },
    {
      section: 'Oversight',
      links: [
        { to: '/activity', label: 'Activity log', icon: <Activity size={16} />, permission: 'audit:read' },
        { to: '/system', label: 'System status', icon: <ServerCog size={16} />, permission: 'system:read' },
        { to: '/admin/operations', label: 'Operations setup', icon: <Settings size={16} />, permission: 'operations:manage' },
        { to: '/admin/users', label: 'Users', icon: <Users size={16} />, permission: 'users:manage' },
      ],
    },
  ];

  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="shell-header">
        <Button variant="ghost" className="menu-toggle" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} icon={<Menu size={18} />} />
        <NavLink to="/" className="brand"><Logo /> RAAHAT</NavLink>
        <div className="grow row" style={{ minWidth: 0 }}><OperationSelect /></div>
        <ConnectionIndicator />
        {user && (
          <div className="row hide-narrow" title={ROLE[user.role].description}>
            <div className="stack-sm" style={{ gap: 0, textAlign: 'right' }}>
              <span className="small" style={{ fontWeight: 600 }}>{user.full_name}</span>
              <span className="xs muted">{ROLE[user.role].label}</span>
            </div>
          </div>
        )}
        <Button variant="ghost" onClick={logout} aria-label="Sign out" title="Sign out" icon={<LogOut size={16} />} />
      </header>
      <div className="shell-banner"><OfflineBanner /></div>
      <nav className="shell-nav" data-open={open} aria-label="Main">
        {items.map((group) => {
          const visible = group.links.filter((l) => !l.permission || can(l.permission));
          if (!visible.length) return null;
          return (
            <div key={group.section}>
              <div className="nav-section">{group.section}</div>
              <ul className="nav-list">
                {visible.map((link) => (
                  <li key={link.to}>
                    <NavLink to={link.to} end={link.end} className="nav-link">
                      {link.icon}
                      {link.label}
                      {!!link.count && <span className="count badge tone-warn num" title="Awaiting review">{link.count}</span>}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </nav>
      <main id="main" className="shell-main" tabIndex={-1}>{children}</main>
    </div>
  );
}
