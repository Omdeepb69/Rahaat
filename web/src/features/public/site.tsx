import { useQuery } from '@tanstack/react-query';
import { Phone } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { Logo } from '../../components/Shell';
import { request } from '../../lib/api';
import { useJurisdictions } from '../../lib/jurisdictions';
import './public.css';

export interface ReportingInfo {
  public_reporting: boolean;
  default_language: string;
  languages: { code: string; name: string; question: string }[];
}

export function useReporting() {
  return useQuery({
    queryKey: ['reporting'],
    queryFn: () => request<ReportingInfo>('/api/v1/reporting', { auth: false }),
    staleTime: 5 * 60_000,
    refetchInterval: false,
  });
}

export function SiteHeader({ nav = true, children }: { nav?: boolean; children?: ReactNode }) {
  return (
    <header className="site-header">
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="wrap">
        <Link to="/" className="site-brand" aria-label="RAAHAT home"><Logo size={26} /> RAAHAT</Link>
        {nav && (
          <nav className="site-nav" aria-label="On this page">
            <a href="#how">How it works</a>
            <a href="#languages">Languages</a>
            <a href="#privacy">Your report</a>
            <a href="#questions">Questions</a>
          </nav>
        )}
        <div className="site-actions">
          <a className="call-112" href="tel:112"><Phone size={15} aria-hidden /><span className="hide-narrow">Call&nbsp;</span>112</a>
          {children}
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  const directory = useJurisdictions();
  return (
    <footer className="site-footer">
      <div className="wrap">
        <div className="stack-sm">
          <span className="site-brand"><Logo size={22} /> RAAHAT</span>
          <p>
            Disaster reporting and coordination for state and district control rooms. RAAHAT supports the
            people who decide; it does not replace emergency services. If a life is in danger, call 112.
          </p>
          {directory.data && (
            <p className="xs">States and districts: {directory.data.source}, {directory.data.licence}.</p>
          )}
        </div>
        <nav aria-label="Site">
          <Link to="/report">Report an emergency</Link>
          <Link to="/login">Authority login</Link>
          <a href="tel:112">Call 112</a>
        </nav>
      </div>
    </footer>
  );
}

export function Site({ children }: { children: ReactNode }) {
  return <div className="site">{children}</div>;
}
