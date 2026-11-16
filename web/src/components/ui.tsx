import {
  AlertTriangle, CheckCircle2, Search, CircleDashed, CircleHelp, Cpu, Info, Loader2, OctagonAlert, TriangleAlert, UserCheck, X,
} from 'lucide-react';
import {
  createContext, useCallback, useContext, useEffect, useId, useRef, useState,
  type ButtonHTMLAttributes, type ComponentProps, type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';

import { errorMessage } from '../lib/api';
import { formatAge, formatFull } from '../lib/format';
import { extractorLabel, HEALTH, INCIDENT_STATUS, isMachine, PRIORITY } from '../lib/labels';
import { useNow } from '../lib/live';
import type { HealthStatus, IncidentStatus, Priority } from '../lib/types';

// ------------------------------------------------------------------ buttons
type ButtonVariant = 'default' | 'primary' | 'accent' | 'danger' | 'ghost';
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: 'sm' | 'md';
  icon?: ReactNode;
  busy?: boolean;
}

export function Button({ variant = 'default', size = 'md', icon, busy, children, className = '', disabled, type = 'button', ...rest }: ButtonProps) {
  const classes = ['btn', variant !== 'default' && `btn-${variant}`, size === 'sm' && 'btn-sm', !children && 'btn-icon', className]
    .filter(Boolean)
    .join(' ');
  return (
    <button type={type} className={classes} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy ? <Loader2 size={14} className="spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

// ------------------------------------------------------------------ fields
interface FieldProps {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: (props: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean; 'aria-required'?: boolean }) => ReactNode;
  required?: boolean;
}

export function Field({ label, hint, error, children, required }: FieldProps) {
  const id = useId();
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required && <span aria-hidden className="required-mark">*</span>}
      </label>
      {children({ id, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined, 'aria-required': required || undefined })}
      {hint && <span id={`${id}-hint`} className="hint">{hint}</span>}
      {error && <span id={`${id}-error`} className="error" role="alert">{error}</span>}
    </div>
  );
}

export const Input = (props: ComponentProps<'input'>) => <input className="input" {...props} />;
export const Textarea = (props: ComponentProps<'textarea'>) => <textarea className="textarea" {...props} />;
export const Select = (props: ComponentProps<'select'>) => <select className="select" {...props} />;

export function SearchInput({ shortcut, ...props }: ComponentProps<'input'> & { shortcut?: string }) {
  return (
    <div className="search">
      <Search size={15} aria-hidden />
      <input className="input" type="search" autoComplete="off" spellCheck={false} enterKeyHint="search" {...props} />
      {shortcut && !props.value && <kbd className="kbd" aria-hidden>{shortcut}</kbd>}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ badges
export function PriorityBadge({ priority, source }: { priority: Priority; source?: string }) {
  const meta = PRIORITY[priority];
  const Icon = priority === 'critical_review' ? OctagonAlert : priority === 'urgent' ? TriangleAlert : priority === 'unassessed' ? CircleHelp : CircleDashed;
  return (
    <span className={`badge sev-${priority}`} title={meta.description + (source === 'operator' ? ' Set by an operator.' : '')}>
      <Icon size={12} aria-hidden />
      {meta.label}
      {source === 'operator' && <UserCheck size={11} aria-label="set by operator" />}
    </span>
  );
}

export function StatusBadge({ status }: { status: IncidentStatus }) {
  const meta = INCIDENT_STATUS[status];
  return <span className={`badge ${meta.tone}`}>{meta.label}</span>;
}

export function HealthBadge({ status }: { status: HealthStatus }) {
  const meta = HEALTH[status];
  return (
    <span className={`badge ${meta.tone}`}>
      <span className="dot" aria-hidden />
      {meta.label}
    </span>
  );
}

export function Badge({ tone = 'tone-outline', children, title }: { tone?: string; children: ReactNode; title?: string }) {
  return <span className={`badge ${tone}`} title={title}>{children}</span>;
}

/** Marks where a value came from: a model or rule, or a person. */
export function ProvenanceTag({ extractor, model }: { extractor: string; model?: string | null }) {
  if (!isMachine(extractor)) return <span className="badge tag-human" title="Entered by a person"><UserCheck size={11} aria-hidden />{extractorLabel(extractor)}</span>;
  return (
    <span className="badge tag-machine" title={model ? `${extractorLabel(extractor)} (${model})` : 'Machine-extracted. Not confirmed by a person.'}>
      <Cpu size={11} aria-hidden />
      {extractorLabel(extractor)}
    </span>
  );
}

export function Unknown({ children = 'Unknown' }: { children?: ReactNode }) {
  return <span className="unknown">{children}</span>;
}

// ------------------------------------------------------------------ time
export function TimeAgo({ value, prefix }: { value: string | number; prefix?: string }) {
  const now = useNow(15_000);
  const date = typeof value === 'number' ? new Date(value) : new Date(value);
  return (
    <time dateTime={date.toISOString()} title={formatFull(date)}>
      {prefix}
      {formatAge(date, now)} ago
    </time>
  );
}

// ------------------------------------------------------------------ containers
export function Panel({ title, actions, children, flush, footer, id }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; flush?: boolean; footer?: ReactNode; id?: string;
}) {
  return (
    <section className="panel" aria-labelledby={title && id ? id : undefined}>
      {(title || actions) && (
        <div className="panel-header">
          {typeof title === 'string' ? <h2 id={id}>{title}</h2> : title}
          {actions && <div className="row-wrap">{actions}</div>}
        </div>
      )}
      <div className={`panel-body${flush ? ' flush' : ''}`}>{children}</div>
      {footer && <div className="panel-footer">{footer}</div>}
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · RAAHAT`;
  }, [title]);
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="row-wrap">{actions}</div>}
    </header>
  );
}

// ------------------------------------------------------------------ states
export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      {icon && <div className="state-icon" aria-hidden>{icon}</div>}
      <h2 className="state-title">{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = 'Could not load this' }: { error: unknown; onRetry?: () => void; title?: string }) {
  return (
    <div className="state" role="alert">
      <div className="state-icon" aria-hidden><AlertTriangle size={22} /></div>
      <h2 className="state-title">{title}</h2>
      <p>{errorMessage(error)}</p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="state loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      <span className="small">{label}…</span>
    </div>
  );
}

export function SkeletonList({ rows = 6, label = 'Loading' }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row" aria-hidden>
          <div className="skeleton" style={{ inlineSize: `${38 + ((i * 17) % 30)}%` }} />
          <div className="skeleton" style={{ inlineSize: `${70 + ((i * 11) % 25)}%`, blockSize: '0.75rem' }} />
          <div className="skeleton" style={{ inlineSize: '45%', blockSize: '0.75rem' }} />
        </div>
      ))}
    </div>
  );
}

export function Callout({ tone = 'info', children, title }: { tone?: 'info' | 'warn' | 'bad' | 'machine'; children: ReactNode; title?: string }) {
  const Icon = tone === 'warn' ? TriangleAlert : tone === 'bad' ? OctagonAlert : tone === 'machine' ? Cpu : Info;
  return (
    <div className={`callout${tone !== 'info' ? ` callout-${tone}` : ''}`} role={tone === 'bad' ? 'alert' : undefined}>
      <Icon size={16} aria-hidden />
      <div className="stack-sm">
        {title && <strong>{title}</strong>}
        <div>{children}</div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ dialog
export function Dialog({ title, description, open, onClose, children, footer, wide }: {
  title: string; description?: ReactNode; open: boolean; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const node = ref.current;
    if (!node || !open) return;
    const previous = document.activeElement as HTMLElement | null;
    if (!node.open) node.showModal();
    const field = node.querySelector<HTMLElement>('.dialog-body input:not([disabled]), .dialog-body textarea, .dialog-body select');
    field?.focus();
    const onCancel = (event: Event) => {
      event.preventDefault();
      closeRef.current();
    };
    node.addEventListener('cancel', onCancel);
    return () => {
      node.removeEventListener('cancel', onCancel);
      if (node.open) node.close();
      previous?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <dialog
      ref={ref}
      className={`dialog${wide ? ' dialog-wide' : ''}`}
      aria-labelledby={titleId}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          const box = event.currentTarget.getBoundingClientRect();
          const inside = event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom;
          if (!inside) onClose();
        }
      }}
    >
      <div className="dialog-header">
        <div className="stack-sm">
          <h2 id={titleId}>{title}</h2>
          {description && <p className="muted small">{description}</p>}
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close" icon={<X size={16} />} />
      </div>
      <div className="dialog-body">{children}</div>
      {footer && <div className="dialog-footer">{footer}</div>}
    </dialog>,
    document.body,
  );
}

// ------------------------------------------------------------------ toasts
interface Toast { id: number; tone: 'success' | 'error' | 'info'; message: string }
const ToastContext = createContext<(tone: Toast['tone'], message: string) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast['tone'], message: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, tone, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'error' ? 9000 : 5000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`} role={t.tone === 'error' ? 'alert' : undefined}>
            {t.tone === 'success' ? <CheckCircle2 size={16} aria-hidden /> : t.tone === 'error' ? <AlertTriangle size={16} aria-hidden /> : <Info size={16} aria-hidden />}
            <span className="grow">{t.message}</span>
            <Button variant="ghost" size="sm" aria-label="Dismiss" icon={<X size={14} />} onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

// ------------------------------------------------------------------ tabs
export function Tabs<T extends string>({ tabs, value, onChange, label }: {
  tabs: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          type="button"
          className="tab"
          aria-selected={t.value === value}
          tabIndex={t.value === value ? 0 : -1}
          onClick={() => onChange(t.value)}
          onKeyDown={(e) => {
            const index = tabs.findIndex((x) => x.value === value);
            if (e.key === 'ArrowRight') onChange(tabs[(index + 1) % tabs.length]!.value);
            if (e.key === 'ArrowLeft') onChange(tabs[(index - 1 + tabs.length) % tabs.length]!.value);
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ pagination
export function Pager({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  if (total <= limit) return <span className="small muted num">{total} total</span>;
  const from = offset + 1;
  const to = Math.min(total, offset + limit);
  return (
    <div className="row">
      <span className="small muted num">{from}–{to} of {total}</span>
      <Button size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</Button>
      <Button size="sm" disabled={to >= total} onClick={() => onChange(offset + limit)}>Next</Button>
    </div>
  );
}
