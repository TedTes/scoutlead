import type { ReactNode } from "react";
import { X } from "lucide-react";
import type { Tone } from "../types/navigation";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function Card({ title, meta, children }: { title: string; meta?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <header>
        <h2>{title}</h2>
        {meta}
      </header>
      {children}
    </section>
  );
}

export function StatCard({ label, value, delta, muted }: { label: string; value: string; delta?: string; muted?: boolean }) {
  return (
    <div className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {delta && <em className={muted ? "muted" : ""}>▲ {delta}</em>}
    </div>
  );
}

export function ConversationStat({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="conversation-stat">
      <span>
        <i className={`dot tone-${tone}`} />
        {label}
      </span>
      <strong>{value}</strong>
    </div>
  );
}

export function Field({ label, value, area, hint }: { label: string; value: string; area?: boolean; hint?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {area ? <textarea defaultValue={value} rows={4} /> : <input defaultValue={value} />}
      {hint && <em>{hint}</em>}
    </label>
  );
}

export function ChipSet({
  values,
  tone = "blue",
  removable,
  small,
}: {
  values: string[];
  tone?: Tone | "green";
  removable?: boolean;
  small?: boolean;
}) {
  return (
    <div className={small ? "chips small" : "chips"}>
      {values.map((value) => (
        <span className={`chip tone-${tone}`} key={value}>
          {value}
          {removable && <X size={12} />}
        </span>
      ))}
    </div>
  );
}

export function StatusPill({ children, tone }: { children: ReactNode; tone: Tone }) {
  return <span className={`pill tone-${tone}`}>{children}</span>;
}

export function Subhead({ children }: { children: ReactNode }) {
  return <h3 className="subhead">{children}</h3>;
}

export function LimitRow({ label, value, width, tone }: { label: string; value: string; width: number; tone: Tone }) {
  return (
    <div className="limit-row">
      <span>{label}</span>
      <div className="limit-track">
        <i className={`tone-${tone}`} style={{ width: `${width}%` }} />
      </div>
      <strong>{value}</strong>
    </div>
  );
}
