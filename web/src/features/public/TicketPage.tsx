import { Phone } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Callout, Loading } from '../../components/ui';
import { errorMessage, request } from '../../lib/api';
import { formatFull } from '../../lib/format';
import { Site, SiteFooter, SiteHeader } from './site';

interface Ticket { ticket: string; received_at: string; stage: string; message: string }

const STAGES = [
  { key: 'received', label: 'Received' },
  { key: 'under_review', label: 'Being reviewed' },
  { key: 'confirmed', label: 'Confirmed' },
  { key: 'responding', label: 'Responders assigned' },
];

export function TicketPage() {
  const { ticket = '' } = useParams();
  const [status, setStatus] = useState<Ticket | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    document.title = 'Report status · RAAHAT';
    const load = () => request<Ticket>(`/api/v1/public/tickets/${encodeURIComponent(ticket)}`, { auth: false })
      .then((t) => { setStatus(t); setError(null); })
      .catch((e) => setError(errorMessage(e)));
    void load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [ticket]);
  const reached = status ? Math.max(0, STAGES.findIndex((s) => s.key === status.stage)) : -1;
  return (
    <Site>
      <SiteHeader nav={false} />
      <main id="main" className="report-main">
        <div className="wrap report-column">
          <header>
            <h1>Report status</h1>
            <p>This page checks for updates every 30 seconds.</p>
          </header>
          <section className="report-card" aria-live="polite">
            {error && <Callout tone="bad">{error}</Callout>}
            {!status && !error && <Loading />}
            {status && (
              <>
                <p style={{ fontSize: '1.25rem', fontWeight: 600, lineHeight: 1.4 }}>{status.message}</p>
                {status.stage !== 'closed' && (
                  <ol className="next-steps" style={{ listStyle: 'none', paddingInlineStart: 0 }}>
                    {STAGES.map((s, i) => (
                      <li key={s.key} style={{ color: i <= reached ? 'var(--text)' : undefined, fontWeight: i === reached ? 650 : undefined }}>
                        {i <= reached ? '●' : '○'} {s.label}
                      </li>
                    ))}
                  </ol>
                )}
                <p className="small muted">Received {formatFull(status.received_at)}.</p>
                <span className="ticket">{status.ticket}</span>
              </>
            )}
            <Link to="/report" className="btn btn-lg">Make another report</Link>
          </section>
          <p className="danger-note"><Phone size={18} aria-hidden /><span>If a life is in danger, <a href="tel:112">call 112</a>.</span></p>
        </div>
      </main>
      <SiteFooter />
    </Site>
  );
}
