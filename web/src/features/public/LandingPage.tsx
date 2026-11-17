import { ArrowRight, Eye, FileAudio, LocateFixed, MapPin, Phone, Plus, ShieldCheck, UserCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { useJurisdictions } from '../../lib/jurisdictions';
import { Site, SiteFooter, SiteHeader, useReporting, type ReportingInfo } from './site';

const WAVE = [0.45, 0.7, 0.55, 0.9, 0.65, 0.8, 0.5, 0.95, 0.6, 0.75, 0.5, 0.85, 0.6, 0.7, 0.45, 0.8, 0.55, 0.65];

function CallCard({ reporting }: { reporting: ReportingInfo | undefined }) {
  const languages = reporting?.languages ?? [];
  const [index, setIndex] = useState(0);
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    if (languages.length < 2) return;
    let swap: ReturnType<typeof setTimeout>;
    const timer = setInterval(() => {
      if (document.hidden) return;
      setLeaving(true);
      swap = setTimeout(() => { setIndex((i) => (i + 1) % languages.length); setLeaving(false); }, 360);
    }, 3200);
    return () => { clearInterval(timer); clearTimeout(swap); };
  }, [languages.length]);
  const current = languages[index];
  return (
    <figure className="call-card" aria-labelledby="call-card-caption">
      <figcaption id="call-card-caption" className="sr-only">
        The reporting assistant asks its questions aloud, in the caller's own language.
      </figcaption>
      <div className="call-card-top" aria-hidden>
        <span className="call-card-place"><MapPin size={15} /> Your district</span>
        <span className="call-card-live">Listening</span>
      </div>
      <div className="call-card-question" aria-hidden>
        {current ? (
          <p data-leaving={leaving} lang={current.code}>
            {current.question}
            <span className="lang" lang="en"><br />{current.name}</span>
          </p>
        ) : (
          <p>Please tell us what has happened.</p>
        )}
      </div>
      <div className="wave" aria-hidden>
        {WAVE.map((h, i) => <span key={i} style={{ ['--i' as string]: i, ['--h' as string]: `${h * 100}%` }} />)}
      </div>
      {languages.length > 0 && (
        <div className="lang-strip" aria-hidden>
          {languages.map((l, i) => <span key={l.code} lang={l.code} aria-current={i === index}>{l.name}</span>)}
        </div>
      )}
    </figure>
  );
}

function ReportButton({ where }: { where: string }) {
  return (
    <Link to="/report" className="btn btn-cta btn-lg" data-cta={where}>
      <Phone size={18} aria-hidden /> Report an emergency
    </Link>
  );
}

export function LandingPage() {
  const reporting = useReporting();
  const directory = useJurisdictions();
  const heroActions = useRef<HTMLDivElement>(null);
  const [heroVisible, setHeroVisible] = useState(true);

  useEffect(() => {
    document.title = 'RAAHAT: report an emergency in your own language';
    const target = heroActions.current;
    if (!target || !('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver(([entry]) => setHeroVisible(entry?.isIntersecting ?? true), { threshold: 0 });
    observer.observe(target);
    return () => observer.disconnect();
  }, []);

  const languages = reporting.data?.languages ?? [];
  const states = directory.data?.states.length;
  const districts = directory.data?.states.reduce((n, s) => n + s.districts.length, 0);
  const closed = reporting.data && !reporting.data.public_reporting;

  return (
    <Site>
      <SiteHeader>
        <Link to="/login" className="btn btn-ghost btn-sm hide-narrow">Authority login</Link>
        <Link to="/report" className="btn btn-cta btn-sm">Report</Link>
      </SiteHeader>
      <main id="main">
        <section className="hero" aria-labelledby="hero-title">
          <div className="wrap hero-grid">
            <div>
              <h1 id="hero-title">Report an emergency in the language you speak.</h1>
              <p className="lede">
                Answer a few short questions out loud. RAAHAT understands your language, notes where you are and
                who needs help, and sends it straight to the disaster control room for your district.
              </p>
              <div className="hero-actions" ref={heroActions}>
                <ReportButton where="hero" />
                <a href="#how" className="row small" style={{ fontWeight: 600 }}>How it works <ArrowRight size={15} aria-hidden /></a>
              </div>
              <p className="hero-micro">Free. No app and no sign-up. You can type instead of speaking.</p>
              {closed && (
                <p className="hero-micro" role="note">Online reporting is not switched on for this service at the moment. Please call 112.</p>
              )}
              <p className="danger-note"><Phone size={18} aria-hidden /><span>Is someone's life in danger right now? <a href="tel:112">Call 112</a> first.</span></p>
            </div>
            <CallCard reporting={reporting.data} />
          </div>
        </section>

        <section className="section section-alt" id="how" aria-labelledby="how-title">
          <div className="wrap">
            <h2 id="how-title">Three steps, about two minutes.</h2>
            <p className="section-lede">No forms to fill in. The assistant asks one thing at a time and skips anything you have already said.</p>
            <ol className="steps">
              <li>
                <h3>Choose your district</h3>
                <p>Pick your state and district. Your report goes only to the control room responsible for that place. Share your phone's location too, if you want.</p>
              </li>
              <li>
                <h3>Answer out loud</h3>
                <p>What happened, where exactly you are, how many people are with you, whether anyone is hurt or trapped, and a number to call you back on.</p>
              </li>
              <li>
                <h3>The control room takes it from there</h3>
                <p>Staff see your words, your location and the recording within seconds, and decide who to send. You get a ticket to check the status of your report.</p>
              </li>
            </ol>
          </div>
        </section>

        <section className="section" id="languages" aria-labelledby="languages-title">
          <div className="wrap">
            <h2 id="languages-title">Speak naturally. It recognises your language.</h2>
            <p className="section-lede">
              The language is detected from your first answer, and every question after that is asked in it. If your
              language isn't recognised, the assistant continues in Hindi. You can choose a language yourself at any time.
            </p>
            {languages.length > 0 ? (
              <ul className="languages">
                {languages.map((l) => (
                  <li key={l.code} lang={l.code}>
                    <span className="name">{l.name}</span>
                    <span className="q">{l.question}</span>
                  </li>
                ))}
              </ul>
            ) : reporting.isError ? (
              <p className="coverage">The list of languages could not be loaded right now.</p>
            ) : null}
          </div>
        </section>

        <section className="section section-alt" id="privacy" aria-labelledby="privacy-title">
          <div className="wrap">
            <h2 id="privacy-title">What happens to your report.</h2>
            <div className="assurances">
              <div className="assurance">
                <span className="icon"><Eye size={20} aria-hidden /></span>
                <h3>Only your area's control rooms see it</h3>
                <p>Your district's control room, its state control room and the national administration. Control rooms in other states cannot open it.</p>
              </div>
              <div className="assurance">
                <span className="icon"><UserCheck size={20} aria-hidden /></span>
                <h3>A person reviews every report</h3>
                <p>Nothing is dispatched automatically. Control room staff check what you said and decide who to send.</p>
              </div>
              <div className="assurance">
                <span className="icon"><LocateFixed size={20} aria-hidden /></span>
                <h3>Your location only if you allow it</h3>
                <p>Sharing your phone's position is optional. Without it, the landmarks you mention are matched on the map.</p>
              </div>
              <div className="assurance">
                <span className="icon"><FileAudio size={20} aria-hidden /></span>
                <h3>Your own words are kept</h3>
                <p>The control room hears your recording and reads exactly what you said, in your language, next to anything worked out from it.</p>
              </div>
            </div>
            {states && districts ? (
              <p className="coverage">
                Covers all <strong>{states}</strong> states and union territories and <strong>{districts}</strong> districts,
                using the Government of India's Local Government Directory.
              </p>
            ) : null}
          </div>
        </section>

        <section className="section" id="questions" aria-labelledby="questions-title">
          <div className="wrap">
            <h2 id="questions-title">Questions people ask.</h2>
            <div className="faq">
              <details>
                <summary>Does this replace calling 112?<Plus size={18} aria-hidden /></summary>
                <p>No. If someone's life is in danger, call 112 first. RAAHAT gets the details to your district's disaster control room, which matters most during floods and other disasters when phone lines are overloaded.</p>
              </details>
              <details>
                <summary>Do I need to install an app or create an account?<Plus size={18} aria-hidden /></summary>
                <p>No. It works in your phone's browser. Allow the microphone when your phone asks, or type your answers instead.</p>
              </details>
              <details>
                <summary>What if my connection drops during the call?<Plus size={18} aria-hidden /></summary>
                <p>Whatever you have already said is sent to the control room automatically a few minutes later. You can also press “Send report now” at any point.</p>
              </details>
              <details>
                <summary>Which languages can I use?<Plus size={18} aria-hidden /></summary>
                <p>{languages.length ? `${languages.map((l) => l.name).join(', ')}.` : 'Most major Indian languages.'} If your language isn't recognised, the questions are asked in Hindi and you can answer however you can, or type.</p>
              </details>
              <details>
                <summary>Who can see what I say?<Plus size={18} aria-hidden /></summary>
                <p>Only the control rooms responsible for the district you chose, and the national administration. Every time staff open or change a report, it is recorded.</p>
              </details>
              <details>
                <summary>Is it free?<Plus size={18} aria-hidden /></summary>
                <p>Yes. There is no charge, and no sign-up.</p>
              </details>
            </div>
          </div>
        </section>

        <section className="section section-alt closing" aria-labelledby="closing-title">
          <div className="wrap">
            <h2 id="closing-title">Need help now?</h2>
            <p className="section-lede">Tell us what is happening, in your language. If a life is in danger, call 112 first.</p>
            <div className="hero-actions">
              <ReportButton where="closing" />
              <a className="btn btn-lg" href="tel:112"><Phone size={18} aria-hidden /> Call 112</a>
            </div>
            <p className="hero-micro"><ShieldCheck size={14} aria-hidden style={{ display: 'inline', verticalAlign: '-2px' }} /> Control room staff: <Link to="/login">authority login</Link>.</p>
          </div>
        </section>
      </main>
      <SiteFooter />
      <div className="sticky-cta" data-hidden={heroVisible} aria-hidden={heroVisible}>
        <Link to="/report" className="btn btn-cta btn-lg" tabIndex={heroVisible ? -1 : 0}><Phone size={18} aria-hidden /> Report an emergency</Link>
        <a href="tel:112" className="btn btn-lg" tabIndex={heroVisible ? -1 : 0} aria-label="Call 112">112</a>
      </div>
    </Site>
  );
}
