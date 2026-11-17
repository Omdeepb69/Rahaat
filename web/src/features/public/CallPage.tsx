import { Check, Keyboard, Loader2, LocateFixed, Mic, Phone, Send, Volume2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { Button, Callout, Field, Input, Select } from '../../components/ui';
import { errorMessage } from '../../lib/api';
import { findState, rememberedPlace, rememberPlace, useJurisdictions } from '../../lib/jurisdictions';
import { Site, SiteFooter, SiteHeader, useReporting } from './site';
import { useCall, type CallFacts, type Phase, type Position } from './useCall';

type Locating = 'idle' | 'locating' | 'denied' | 'unavailable';

const STATUS: Record<Phase, string> = {
  idle: '',
  connecting: 'Connecting…',
  speaking: 'Speaking',
  listening: 'Listening. Speak now.',
  hearing: 'Listening…',
  sending: 'Understanding what you said…',
  waiting: 'Your turn',
  done: 'Report sent',
  failed: 'The call stopped',
};

function useLocation() {
  const [state, setState] = useState<Locating>('idle');
  const locate = (onFound: (p: Position) => void) => {
    if (!('geolocation' in navigator)) { setState('unavailable'); return; }
    setState('locating');
    navigator.geolocation.getCurrentPosition(
      (p) => { setState('idle'); onFound({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy_m: p.coords.accuracy ?? null }); },
      (e) => setState(e.code === e.PERMISSION_DENIED ? 'denied' : 'unavailable'),
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 60_000 },
    );
  };
  return { state, locate };
}

function PositionLine({ position, locating, onLocate }: { position: Position | null; locating: Locating; onLocate: () => void }) {
  if (position) {
    return (
      <p className="position-row">
        <span className="ok"><Check size={15} aria-hidden /> Location shared</span>
        {position.accuracy_m ? <span className="num">within about {Math.round(position.accuracy_m)} m</span> : null}
      </p>
    );
  }
  return (
    <div className="position-row">
      <Button size="sm" icon={<LocateFixed size={14} aria-hidden />} busy={locating === 'locating'} onClick={onLocate}>
        Share my location
      </Button>
      <span>
        {locating === 'denied' && 'Location permission was refused. Describe where you are instead.'}
        {locating === 'unavailable' && 'Your location could not be found. Describe where you are instead.'}
        {(locating === 'idle' || locating === 'locating') && 'Optional. Helps rescuers find you.'}
      </span>
    </div>
  );
}

function Facts({ facts, district, state }: { facts: CallFacts; district: string; state: string }) {
  const hurt = [facts.trapped && 'someone is trapped', facts.medical && 'someone needs medical help'].filter(Boolean).join(', ');
  const rows: [string, string | null][] = [
    ['Control room', `${district}, ${state}`],
    ['Where', facts.place],
    ['People', facts.people_count ? String(facts.people_count) : null],
    ['Danger', hurt || null],
    ['Call back on', facts.phone],
    ['Name', facts.name],
  ];
  return (
    <dl className="facts-list">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd data-empty={!value}>{value ?? 'Not yet'}</dd>
        </div>
      ))}
    </dl>
  );
}

export function CallPage() {
  const directory = useJurisdictions();
  const reporting = useReporting();
  const call = useCall();
  const { controller } = call;
  const location = useLocation();
  const remembered = useMemo(() => rememberedPlace('report'), []);
  const [stateCode, setStateCode] = useState(remembered?.state ?? '');
  const [districtCode, setDistrictCode] = useState(remembered?.district ?? '');
  const [setupError, setSetupError] = useState<string | null>(null);
  const [typed, setTyped] = useState('');
  const typeInput = useRef<HTMLInputElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  const state = findState(directory.data, stateCode);
  const started = call.phase !== 'idle' && !(call.phase === 'failed' && !call.call);

  useEffect(() => { document.title = 'Report an emergency · RAAHAT'; }, []);
  useEffect(() => { heading.current?.focus(); }, [started, call.phase === 'done']); // eslint-disable-line react-hooks/exhaustive-deps

  const begin = async (event: FormEvent) => {
    event.preventDefault();
    if (!stateCode || !districtCode) { setSetupError('Choose your state and district so the right control room receives your report.'); return; }
    setSetupError(null);
    rememberPlace('report', { state: stateCode, district: districtCode });
    await controller.start(stateCode, districtCode);
  };

  const submitTyped = async (event: FormEvent) => {
    event.preventDefault();
    const value = typed.trim();
    if (!value) return;
    setTyped('');
    await controller.type(value);
    typeInput.current?.focus();
  };

  const locate = () => location.locate((p) => void controller.sharePosition(p));
  const question = [...call.entries].reverse().find((e) => e.who === 'agent');
  const busy = call.phase === 'sending' || call.phase === 'connecting';
  const listening = call.phase === 'listening' || call.phase === 'hearing';
  const closed = reporting.data && !reporting.data.public_reporting;

  return (
    <Site>
      <SiteHeader nav={false} />
      <main id="main" className="report-main">
        <div className="wrap report-column">
          {!started && (
            <>
              <header>
                <h1 ref={heading} tabIndex={-1}>Report an emergency</h1>
                <p>An assistant will ask a few short questions out loud, in your language. Answer by speaking, or type if you prefer.</p>
              </header>
              {closed && <Callout tone="bad" title="Online reporting is not available right now">Please call 112.</Callout>}
              <form className="report-card" onSubmit={begin} noValidate>
                <h2 style={{ fontSize: '1.125rem' }}>Where are you?</h2>
                {directory.isError && <Callout tone="bad">The list of districts could not be loaded. {errorMessage(directory.error)}</Callout>}
                <Field label="State or union territory" required>
                  {(p) => (
                    <Select {...p} value={stateCode} disabled={directory.isPending} onChange={(e) => { setStateCode(e.target.value); setDistrictCode(''); }}>
                      <option value="" disabled>{directory.isPending ? 'Loading…' : 'Choose your state…'}</option>
                      {directory.data?.states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="District" required>
                  {(p) => (
                    <Select {...p} value={districtCode} disabled={!state} onChange={(e) => setDistrictCode(e.target.value)}>
                      <option value="" disabled>{state ? 'Choose your district…' : 'Choose a state first'}</option>
                      {state?.districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
                    </Select>
                  )}
                </Field>
                <PositionLine position={call.position} locating={location.state} onLocate={locate} />
                {(setupError || call.error) && <Callout tone="bad">{setupError ?? call.error}</Callout>}
                <Button type="submit" variant="primary" className="btn-cta btn-lg" icon={<Mic size={18} aria-hidden />} disabled={!!closed}>
                  Start the call
                </Button>
                <p className="small muted">Your phone will ask to use the microphone. If you can't talk, you can type every answer.</p>
              </form>
              <p className="danger-note"><Phone size={18} aria-hidden /><span>Is someone's life in danger right now? <a href="tel:112">Call 112</a> first.</span></p>
            </>
          )}

          {started && call.phase !== 'done' && call.call && (
            <>
              <section className="report-card" aria-labelledby="call-title">
                <div className="call-meta">
                  <span>Reporting to <strong style={{ color: 'var(--text)' }}>{call.call.district}</strong>, {call.call.state}</span>
                  <label className="row">
                    <span className="sr-only">Language</span>
                    <Select
                      value={call.call.language_source === 'chosen' ? call.call.language : 'auto'}
                      onChange={(e) => void controller.chooseLanguage(e.target.value)}
                      aria-label="Language of the call"
                    >
                      <option value="auto">
                        {call.call.language_source === 'default' ? 'Language: automatic' : `${call.call.language_name} (detected)`}
                      </option>
                      {reporting.data?.languages.map((l) => <option key={l.code} value={l.code} lang={l.code}>{l.name}</option>)}
                    </Select>
                  </label>
                </div>
                <div className="stage">
                  <div className="orb" data-phase={call.phase} style={{ ['--level' as string]: call.level }} aria-hidden>
                    {busy ? <Loader2 size={34} className="spin" /> : call.phase === 'speaking' ? <Volume2 size={34} /> : call.microphone === false ? <Keyboard size={34} /> : <Mic size={34} />}
                  </div>
                  <p className="stage-status" role="status" aria-live="polite">{STATUS[call.phase]}</p>
                  <h1 id="call-title" ref={heading} tabIndex={-1} className="question" lang={question?.language}>
                    {question?.text ?? 'Connecting…'}
                  </h1>
                </div>
                {call.notice && <Callout tone="warn">{call.notice}</Callout>}
                {!call.voiceAvailable && <Callout>The spoken questions are not available right now. Read each question here and answer by speaking or typing.</Callout>}
                {call.microphone === false && (
                  <Callout tone="warn" title="The microphone is not available">
                    Type your answers below. To speak instead, allow the microphone in your browser settings and start again.
                  </Callout>
                )}
                <div className="call-controls">
                  {listening && (
                    <Button variant="primary" className="btn-lg" onClick={() => controller.doneSpeaking()} disabled={call.phase !== 'hearing'}>
                      {call.phase === 'hearing' ? "I've finished speaking" : 'Waiting for you to speak…'}
                    </Button>
                  )}
                  {call.phase === 'waiting' && call.canResend && <Button variant="primary" className="btn-lg" onClick={() => void controller.resend()}>Send my answer again</Button>}
                  {call.phase === 'waiting' && !call.canResend && call.microphone && (
                    <Button className="btn-lg" icon={<Mic size={18} aria-hidden />} onClick={() => void controller.listenAgain()}>Answer by speaking</Button>
                  )}
                  <form className="type-row" onSubmit={submitTyped}>
                    <Input
                      ref={typeInput}
                      value={typed}
                      onChange={(e) => setTyped(e.target.value)}
                      placeholder="Or type your answer"
                      aria-label="Type your answer"
                      enterKeyHint="send"
                      autoComplete="off"
                      disabled={busy}
                      autoFocus={call.microphone === false}
                    />
                    <Button type="submit" aria-label="Send answer" icon={<Send size={16} aria-hidden />} disabled={busy || !typed.trim()} />
                  </form>
                </div>
              </section>

              <section className="report-card facts-card" aria-labelledby="facts-title">
                <h2 id="facts-title">What we have so far</h2>
                <Facts facts={call.call.facts} district={call.call.district} state={call.call.state} />
                <PositionLine position={call.position} locating={location.state} onLocate={locate} />
                <Button className="btn-lg" icon={<Send size={17} aria-hidden />} onClick={() => void controller.finish()} disabled={busy}>
                  Send report now
                </Button>
                <p className="small muted">Sends everything you have said so far. If you close this page, it is sent automatically after a few minutes.</p>
              </section>

              {call.entries.length > 0 && (
                <section className="report-card transcript-card" aria-labelledby="transcript-title">
                  <h2 id="transcript-title">Conversation</h2>
                  <ol className="transcript">
                    {call.entries.map((e) => (
                      <li key={e.id} data-who={e.who} lang={e.language}>
                        {e.text}
                        <span className="via" lang="en">{e.who === 'agent' ? 'Assistant' : e.via === 'text' ? 'You typed' : 'You said'}</span>
                      </li>
                    ))}
                  </ol>
                </section>
              )}
            </>
          )}

          {started && call.phase === 'failed' && (
            <Callout tone="bad" title="The call stopped">
              {call.error} <Link to="/report" reloadDocument>Start again</Link> or call 112.
            </Callout>
          )}

          {call.phase === 'done' && call.call && (
            <section className="report-card" aria-labelledby="done-title">
              <div className="done-mark" aria-hidden>
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
              </div>
              <h1 id="done-title" ref={heading} tabIndex={-1} style={{ fontSize: 'clamp(1.5rem, 1.2rem + 1.4vw, 2rem)', letterSpacing: '-0.02em' }}>
                Your report has been sent
              </h1>
              <p>The {call.call.district} control room, {call.call.state}, has received it.</p>
              {call.call.ticket && (
                <div className="stack-sm">
                  <span className="small muted">Your ticket</span>
                  <span className="ticket">{call.call.ticket}</span>
                </div>
              )}
              <ul className="next-steps">
                <li>Control room staff will review what you said and decide who to send.</li>
                <li>If you gave a phone number, keep it with you. They may call you back.</li>
                <li>If it is safe, stay where you are. If anything changes, report again.</li>
              </ul>
              {call.call.ticket && <Link className="btn btn-primary btn-lg" to={`/report/status/${call.call.ticket}`}>Check the status of my report</Link>}
              <p className="danger-note"><Phone size={18} aria-hidden /><span>If a life is in danger, <a href="tel:112">call 112</a> as well.</span></p>
            </section>
          )}
        </div>
      </main>
      <SiteFooter />
    </Site>
  );
}

