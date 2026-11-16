import {
  Activity, ClipboardList, FileText, LayoutDashboard, LogOut, Megaphone, Menu, Monitor, Moon, PlusCircle, Radio,
  ServerCog, Settings, Sun, Truck, Users, X,
} from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { useAuth } from '../lib/auth';
import { formatAge, formatTime } from '../lib/format';
import { ROLE } from '../lib/labels';
import { useConnection, useNow, useStream } from '../lib/live';
import { useOperation } from '../lib/operation';
import { useIncidentCounts } from '../lib/queries';
import { useTheme, type ThemePreference } from '../lib/theme';
import type { Permission } from '../lib/types';
import { Button } from './ui';

export function Logo({ size = 24 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <path d="M9.5 22.5v-13h6.75a4 4 0 0 1 0 8H13m3.25 0 5.25 5" fill="none" stroke="var(--bg, #fff)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="23" cy="9.5" r="2.4" fill="oklch(0.68 0.17 45)" />
    </svg>
  );
}

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
    <span className={`badge ${tone}`} role="status" aria-live="polite" title={title} style={{ blockSize: '1.625rem', paddingInline: '0.625rem' }}>
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
          ? <>Information on screen was last confirmed at <time>{formatTime(connection.lastContactAt)}</time> ({formatAge(connection.lastContactAt, now)} ago) and may be out of date.</>
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
    <div className="header-operation">
      <label htmlFor="operation-select" className="sr-only">Operation</label>
      <select id="operation-select" className="select" value={operation?.id ?? ''} onChange={(e) => select(e.target.value)}>
        {operations.map((o) => (
          <option key={o.id} value={o.id}>{o.name}{o.status === 'closed' ? ' (closed)' : ''}</option>
        ))}
      </select>
    </div>
  );
}

const THEMES: { value: ThemePreference; label: string; icon: ReactNode }[] = [
  { value: 'system', label: 'Match system', icon: <Monitor size={15} /> },
  { value: 'light', label: 'Light', icon: <Sun size={15} /> },
  { value: 'dark', label: 'Dark', icon: <Moon size={15} /> },
];

function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  const index = THEMES.findIndex((t) => t.value === theme);
  const current = THEMES[index]!;
  const next = THEMES[(index + 1) % THEMES.length]!;
  return (
    <Button variant="ghost" icon={current.icon} aria-label={`Theme: ${current.label}. Switch to ${next.label}`} title={`Theme: ${current.label}`} onClick={() => setTheme(next.value)} />
  );
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join('');
}

interface NavItem { to: string; label: string; icon: ReactNode; permission?: Permission; count?: number | null; end?: boolean }

export function Shell({ children }: { children: ReactNode }) {
  const { user, logout, can } = useAuth();
  const { operation } = useOperation();
  const counts = useIncidentCounts(operation?.id ?? null);
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const review = counts.data ? (counts.data.by_status.unverified ?? 0) + (counts.data.by_status.under_review ?? 0) : null;
  const groups: { section: string; links: NavItem[] }[] = [
    {
      section: 'Response',
      links: [
        { to: '/', label: 'Operations board', icon: <LayoutDashboard size={17} />, permission: 'incidents:read', end: true },
        { to: '/intake', label: 'New report', icon: <PlusCircle size={17} />, permission: 'reports:create' },
        { to: '/incidents', label: 'Incidents', icon: <ClipboardList size={17} />, permission: 'incidents:read', count: review },
        { to: '/dispatch', label: 'Dispatch', icon: <Radio size={17} />, permission: 'dispatch:read' },
        { to: '/resources', label: 'Resources', icon: <Truck size={17} />, permission: 'resources:read' },
        { to: '/reports', label: 'Reports', icon: <FileText size={17} />, permission: 'reports:read' },
        { to: '/alerts', label: 'Official alerts', icon: <Megaphone size={17} />, permission: 'incidents:read' },
      ],
    },
    {
      section: 'Oversight',
      links: [
        { to: '/activity', label: 'Activity log', icon: <Activity size={17} />, permission: 'audit:read' },
        { to: '/system', label: 'System status', icon: <ServerCog size={17} />, permission: 'system:read' },
        { to: '/admin/operations', label: 'Operations setup', icon: <Settings size={17} />, permission: 'operations:manage' },
        { to: '/admin/users', label: 'Users', icon: <Users size={17} />, permission: 'users:manage' },
      ],
    },
  ];

  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="shell-header">
        <Button variant="ghost" className="menu-toggle" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} aria-controls="main-nav"
          onClick={() => setOpen((v) => !v)} icon={open ? <X size={18} /> : <Menu size={18} />} />
        <NavLink to="/" className="brand" aria-label="RAAHAT, operations board"><Logo /><span className="brand-name">RAAHAT</span></NavLink>
        <OperationSelect />
        <ConnectionIndicator />
        <ThemeSwitch />
        {user && (
          <div className="user-chip hide-narrow" title={ROLE[user.role].description}>
            <span className="avatar" aria-hidden>{initials(user.full_name)}</span>
            <span className="stack-sm" style={{ gap: 0 }}>
              <span className="small" style={{ fontWeight: 650, lineHeight: 1.25 }}>{user.full_name}</span>
              <span className="xs muted" style={{ lineHeight: 1.25 }}>{ROLE[user.role].label}</span>
            </span>
          </div>
        )}
        <Button variant="ghost" onClick={logout} aria-label="Sign out" title="Sign out" icon={<LogOut size={17} />} />
      </header>
      <div className="shell-banner"><OfflineBanner /></div>
      <button type="button" className="nav-scrim" data-open={open} aria-hidden tabIndex={-1} onClick={() => setOpen(false)} />
      <nav id="main-nav" className="shell-nav" data-open={open} aria-label="Main">
        {groups.map((group) => {
          const visible = group.links.filter((l) => !l.permission || can(l.permission));
          if (!visible.length) return null;
          return (
            <div key={group.section} className="nav-group">
              <div className="nav-section">{group.section}</div>
              <ul className="nav-list">
                {visible.map((link) => (
                  <li key={link.to}>
                    <NavLink to={link.to} end={link.end} className="nav-link">
                      {link.icon}
                      {link.label}
                      {!!link.count && <span className="count badge tone-warn" title={`${link.count} awaiting review`}>{link.count}</span>}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
        <p className="nav-footer">Decision support. Every dispatch needs a person's approval, and RAAHAT does not contact teams for you.</p>
      </nav>
      <main id="main" className="shell-main" tabIndex={-1}>{children}</main>
    </div>
  );
}
