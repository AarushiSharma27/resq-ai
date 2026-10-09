import clsx from 'clsx';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { TONE_CLASSES, toneFor, type Tone } from '../../utils/colors';
import { humanize } from '../../utils/format';

export function Card({ title, actions, children, className, bodyClassName }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string;
}) {
  return (
    <section className={clsx('rounded-xl border border-navy-700 bg-navy-850/80 shadow-lg shadow-black/20', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-navy-700 px-4 py-2.5">
          {title && <h2 className="text-sm font-semibold tracking-wide text-slate-200">{title}</h2>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx('p-4', bodyClassName)}>{children}</div>
    </section>
  );
}

type BtnVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'success';
const BTN: Record<BtnVariant, string> = {
  primary: 'bg-sky-600 hover:bg-sky-500 text-white',
  secondary: 'bg-navy-700 hover:bg-navy-600 text-slate-200 border border-navy-600',
  danger: 'bg-red-600 hover:bg-red-500 text-white',
  success: 'bg-emerald-600 hover:bg-emerald-500 text-white',
  ghost: 'hover:bg-navy-700 text-slate-300',
};

export function Button({ variant = 'primary', loading, size = 'md', className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; loading?: boolean; size?: 'sm' | 'md' }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm',
        BTN[variant], className,
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Badge({ children, tone, value, className }: { children?: ReactNode; tone?: Tone; value?: string | null; className?: string }) {
  const t = tone ?? toneFor(value ?? (typeof children === 'string' ? children : ''));
  return (
    <span className={clsx('inline-flex items-center whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset', TONE_CLASSES[t], className)}>
      {children ?? humanize(value)}
    </span>
  );
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string | null | undefined; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1 break-words">{error}</div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 text-xs text-red-200 underline">
          <RefreshCw className="h-3 w-3" /> Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-6 text-center text-sm text-slate-500">{children}</div>;
}

/** Loading / error / content switch. */
export function Async<T>({ loading, error, data, onRetry, children }: {
  loading: boolean; error: string | null; data: T | null | undefined; onRetry?: () => void; children: (d: T) => ReactNode;
}) {
  if (error) return <ErrorBox error={error} onRetry={onRetry} />;
  if (loading && (data === null || data === undefined)) return <Spinner />;
  if (data === null || data === undefined) return null;
  return <>{children(data)}</>;
}

export const inputCls = 'w-full rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500';

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(inputCls, props.className)} />;
}
export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={clsx(inputCls, 'pr-8', props.className)}>{children}</select>;
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={clsx(inputCls, 'font-mono', props.className)} />;
}

export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={clsx('block', className)}>
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">{label}</span>
      {children}
    </label>
  );
}

export function Kpi({ label, value, sub, icon, tone = 'blue' }: { label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode; tone?: Tone }) {
  const accent: Record<Tone, string> = {
    neutral: 'text-slate-300', green: 'text-emerald-400', yellow: 'text-yellow-400', orange: 'text-orange-400',
    red: 'text-red-400', blue: 'text-sky-400', purple: 'text-violet-400',
  };
  return (
    <div className="rounded-xl border border-navy-700 bg-navy-850/80 p-4">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-slate-400">
        <span>{label}</span>
        {icon && <span className={accent[tone]}>{icon}</span>}
      </div>
      <div className={clsx('mt-2 text-2xl font-bold tabular-nums', accent[tone])}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </div>
  );
}

export function Table({ head, children, className }: { head: ReactNode[]; children: ReactNode; className?: string }) {
  return (
    <div className={clsx('overflow-x-auto', className)}>
      <table className="w-full min-w-max text-left text-sm">
        <thead>
          <tr className="border-b border-navy-700 text-xs uppercase tracking-wide text-slate-400">
            {head.map((h, i) => <th key={i} className="px-3 py-2 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-navy-700/60">{children}</tbody>
      </table>
    </div>
  );
}
export function Td({ children, className, colSpan }: { children?: ReactNode; className?: string; colSpan?: number }) {
  return <td colSpan={colSpan} className={clsx('px-3 py-2 align-top text-slate-200', className)}>{children}</td>;
}

export function Tabs<K extends string>({ tabs, active, onChange }: { tabs: { key: K; label: ReactNode }[]; active: K; onChange: (k: K) => void }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-navy-700" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={clsx(
            '-mb-px border-b-2 px-3 py-2 text-sm transition',
            active === t.key ? 'border-sky-400 text-sky-300' : 'border-transparent text-slate-400 hover:text-slate-200',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Bar({ value, max, color, label }: { value: number; max: number; color?: string; label?: ReactNode }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const c = color ?? (pct > 90 ? '#ef4444' : pct > 75 ? '#f97316' : pct > 50 ? '#eab308' : '#22c55e');
  return (
    <div>
      {label && <div className="mb-1 flex justify-between text-xs text-slate-400">{label}</div>}
      <div className="h-2 w-full overflow-hidden rounded-full bg-navy-700">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: c }} />
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-bold text-slate-100">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5 text-sm">
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-slate-400">{k}</dt>
          <dd className="break-words text-slate-200">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
