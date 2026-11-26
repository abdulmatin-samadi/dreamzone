import { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useDebounced } from "../lib/hooks";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

/* ------------------------------------------------------------------ buttons */
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "success"; size?: "sm" | "md" | "lg"; loading?: boolean;
};
const variants = {
  primary: "bg-gradient-to-r from-blue-600 to-cyan-500 text-on-accent shadow-sm shadow-blue-300/50 hover:from-[#1d4ed8] hover:to-cyan-600 disabled:from-blue-300 disabled:to-cyan-300 disabled:shadow-none",
  secondary: "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 disabled:text-slate-400",
  danger: "bg-red-600 text-on-accent hover:bg-[#b91c1c] disabled:bg-red-300",
  success: "bg-gradient-to-r from-emerald-500 to-teal-500 text-on-accent shadow-sm shadow-emerald-200 hover:from-emerald-600 hover:to-teal-600 disabled:opacity-50",
  ghost: "text-slate-600 hover:bg-slate-100 disabled:text-slate-300",
};
const sizes = { sm: "px-2.5 py-1.5 text-xs", md: "px-4 py-2 text-sm", lg: "px-6 py-3 text-base" };

export function Button({ variant = "primary", size = "md", loading, className, children, disabled, ...rest }: BtnProps) {
  return (
    <button {...rest} disabled={disabled || loading}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed", variants[variant], sizes[size], className)}>
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return <span className={cx("inline-block animate-spin rounded-full border-2 border-current border-t-transparent", className)} aria-hidden />;
}

export function PageLoader() {
  return <div className="flex justify-center py-16 text-indigo-600"><Spinner className="h-8 w-8" /></div>;
}

/* ------------------------------------------------------------------ form fields */
interface FieldProps { label?: string; error?: string; hint?: string; className?: string; required?: boolean }
const inputCls = "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-100";

function FieldWrap({ label, error, hint, className, required, children }: FieldProps & { children: ReactNode }) {
  return (
    <label className={cx("block", className)}>
      {label && <span className="mb-1 block text-sm font-medium text-slate-700">{label}{required && <span className="text-red-500"> *</span>}</span>}
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}

export function Input({ label, error, hint, className, ...rest }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  return <FieldWrap {...{ label, error, hint, className, required: rest.required }}><input {...rest} className={cx(inputCls, error && "border-red-400")} /></FieldWrap>;
}
export function Textarea({ label, error, hint, className, ...rest }: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <FieldWrap {...{ label, error, hint, className, required: rest.required }}><textarea rows={3} {...rest} className={cx(inputCls, error && "border-red-400")} /></FieldWrap>;
}
export function Select({ label, error, hint, className, children, ...rest }: FieldProps & SelectHTMLAttributes<HTMLSelectElement>) {
  return <FieldWrap {...{ label, error, hint, className, required: rest.required }}><select {...rest} className={cx(inputCls, error && "border-red-400")}>{children}</select></FieldWrap>;
}
export function Checkbox({ label, ...rest }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
      <input type="checkbox" {...rest} className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
      {label}
    </label>
  );
}

export function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const { t } = useTranslation();
  const [local, setLocal] = useState(value);
  const debounced = useDebounced(local);
  useEffect(() => { onChange(debounced); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [debounced]);
  return (
    <input type="search" value={local} onChange={(e) => setLocal(e.target.value)} placeholder={placeholder ?? t("common.search")}
      className={cx(inputCls, "w-full sm:w-64")} aria-label={t("common.search")} />
  );
}

/* ------------------------------------------------------------------ layout bits */
export function Card({ children, className, title, actions }: { children: ReactNode; className?: string; title?: ReactNode; actions?: ReactNode }) {
  return (
    <section className={cx("rounded-2xl border border-white/70 bg-white/90 shadow-[0_4px_24px_-8px_rgba(14,90,200,0.15)] backdrop-blur", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}

export function StatCard({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/70 bg-white/90 p-5 shadow-[0_4px_24px_-8px_rgba(14,90,200,0.15)]">
      <span className="absolute inset-y-0 left-0 w-1.5 bg-gradient-to-b from-blue-500 to-cyan-400" aria-hidden />
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 bg-gradient-to-r from-blue-700 to-cyan-500 bg-clip-text text-3xl font-bold text-transparent">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

const tones = {
  gray: "bg-slate-100 text-slate-700", green: "bg-emerald-100 text-emerald-700", red: "bg-red-100 text-red-700",
  amber: "bg-amber-100 text-amber-800", blue: "bg-sky-100 text-sky-700", indigo: "bg-indigo-100 text-indigo-700",
};
export type Tone = keyof typeof tones;
export function Badge({ children, tone = "gray" }: { children: ReactNode; tone?: Tone }) {
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap", tones[tone])}>{children}</span>;
}

export function ProgressBar({ value, tone = "indigo", className }: { value: number; tone?: "indigo" | "green" | "red" | "amber"; className?: string }) {
  const color = { indigo: "bg-gradient-to-r from-blue-500 to-cyan-400", green: "bg-gradient-to-r from-emerald-400 to-teal-500", red: "bg-red-500", amber: "bg-amber-500" }[tone];
  return (
    <div className={cx("h-2 w-full overflow-hidden rounded-full bg-slate-100", className)} role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full rounded-full transition-all", color)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function EmptyState({ text }: { text?: string }) {
  const { t } = useTranslation();
  return <div className="py-10 text-center text-sm text-slate-500">{text ?? t("common.noData")}</div>;
}

/* ------------------------------------------------------------------ table */
export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode; empty?: boolean }) {
  const ref = useRef<HTMLTableElement>(null);
  // On phones every row becomes a card; the column title is shown in front of each value (see index.css).
  useEffect(() => {
    const labels = [...(ref.current?.querySelectorAll("thead th") ?? [])].map((h) => h.textContent ?? "");
    ref.current?.querySelectorAll("tbody tr").forEach((tr) => [...tr.children].forEach((td, i) => td.setAttribute("data-label", labels[i] ?? "")));
  });
  return (
    <div className="overflow-x-auto rounded-2xl border border-white/70 bg-white/90 shadow-[0_4px_24px_-8px_rgba(14,90,200,0.15)]">
      <table ref={ref} className="dz-cards min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-sky-50/70">
          <tr>{head.map((h, i) => <th key={i} className="whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
      {empty && <EmptyState />}
    </div>
  );
}
export const Td = ({ children, className }: { children?: ReactNode; className?: string }) => <td className={cx("px-4 py-3 align-middle text-slate-700", className)}>{children}</td>;

export function Pagination({ page, count, pageSize = 20, onPage }: { page: number; count: number; pageSize?: number; onPage: (p: number) => void }) {
  const { t } = useTranslation();
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="mt-4 flex items-center justify-between text-sm text-slate-600">
      <span>{t("common.pageOf", { page, pages, count })}</span>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>{t("common.previous")}</Button>
        <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>{t("common.next")}</Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ dialogs */
export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const { t } = useTranslation();
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#0b1b38]/50 p-0 sm:items-center sm:p-4" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}
        className={cx("flex max-h-[92vh] w-full flex-col rounded-t-2xl bg-white shadow-xl sm:rounded-2xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg")}>
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label={t("common.close")}>✕</button>
        </header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel, danger, loading, onConfirm, onClose }: {
  open: boolean; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; loading?: boolean; onConfirm: () => void; onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Modal open={open} onClose={onClose} title={title}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant={danger ? "danger" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel ?? t("common.confirm")}</Button></>}>
      <p className="text-sm text-slate-600">{message}</p>
    </Modal>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string }[] }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200">
      {items.map((i) => (
        <button key={i.value} onClick={() => onChange(i.value)}
          className={cx("whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium", value === i.value ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-700")}>
          {i.label}
        </button>
      ))}
    </div>
  );
}

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-end gap-3">{children}</div>;
}

/** Simple horizontal bar chart used on dashboards. */
/** `text` replaces the printed value (e.g. "64 / 80 ball"); `share` (0–1) sets the bar instead of value / biggest value. */
export function BarList({ rows }: { rows: { label: string; value: number; text?: string; share?: number; tone?: "indigo" | "green" | "red" | "amber" }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.label}>
          <div className="mb-1 flex justify-between text-xs text-slate-600"><span>{r.label}</span><span className="font-medium tabular-nums">{r.text ?? r.value}</span></div>
          <ProgressBar value={(r.share ?? r.value / max) * 100} tone={r.tone} />
        </li>
      ))}
    </ul>
  );
}
