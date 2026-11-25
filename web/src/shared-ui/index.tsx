import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";
import type { DiscoveryResult } from "../types/domain";
import type { Tone } from "../types/navigation";
import { baseExportFileName, exportBusinesses, normalizeExportFileName } from "../utils/export-file";
import type { BusinessExportFormat } from "../utils/export-file";

type ToastInput = {
  title: string;
  message?: string;
  tone?: Tone;
};

type ToastItem = ToastInput & {
  id: string;
};

type ToastContextValue = {
  showToast: (toast: ToastInput) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (toast: ToastInput) => {
      const id = typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
      const nextToast = { ...toast, id, tone: toast.tone || "blue" };
      setToasts((current) => [...current.slice(-3), nextToast]);
      window.setTimeout(() => dismissToast(id), 4200);
    },
    [dismissToast],
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="true">
        {toasts.map((toast) => (
          <div className={`toast tone-${toast.tone}`} key={toast.id}>
            <strong>{toast.title}</strong>
            {toast.message ? <span>{toast.message}</span> : null}
            <button className="link-button" type="button" aria-label="Dismiss message" onClick={() => dismissToast(toast.id)}>
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return value;
}

export function Modal({
  title,
  children,
  className = "",
  footer,
  onClose,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  footer?: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className={`modal-card ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <h2>{title}</h2>
          <button className="link-button" type="button" aria-label="Close dialog" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer ? <footer>{footer}</footer> : null}
      </section>
    </div>
  );
}

export function ExportBusinessesDialog({
  businessCount,
  suggestedName,
  scope,
  loadBusinesses,
  onClose,
}: {
  businessCount: number;
  suggestedName: string;
  scope: string;
  loadBusinesses: () => Promise<DiscoveryResult[]>;
  onClose: () => void;
}) {
  const { showToast } = useToast();
  const [fileName, setFileName] = useState(suggestedName);
  const [format, setFormat] = useState<BusinessExportFormat>("csv");
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const hasFileName = Boolean(baseExportFileName(fileName));
  const downloadName = normalizeExportFileName(fileName, format);

  const download = async () => {
    if (!hasFileName || exporting) return;
    setError("");
    setExporting(true);
    try {
      const businesses = await loadBusinesses();
      if (!businesses.length) {
        setError("There are no businesses to export in this selection.");
        return;
      }
      exportBusinesses(businesses, downloadName, format);
      showToast({ title: "Export downloaded", message: downloadName, tone: "green" });
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load businesses for export.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <Modal title="Export businesses" onClose={exporting ? () => undefined : onClose}>
      <form
        className="export-contacts-form"
        onSubmit={(event) => {
          event.preventDefault();
          void download();
        }}
      >
        <p>{scope} · {businessCount} {businessCount === 1 ? "business" : "businesses"}</p>
        <label className="field">
          <span>Format</span>
          <select value={format} disabled={exporting} onChange={(event) => setFormat(event.target.value === "json" ? "json" : "csv")}>
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
        </label>
        <label className="field">
          <span>File name</span>
          <input
            autoFocus
            disabled={exporting}
            placeholder={suggestedName}
            value={fileName}
            onChange={(event) => setFileName(event.target.value)}
          />
          {!hasFileName ? <em>Enter a filename.</em> : null}
        </label>
        <p className="export-file-preview">
          {hasFileName ? downloadName : `filename.${format}`}
        </p>
        {error ? <p role="alert">{error}</p> : null}
        <div className="dialog-actions">
          <button className="secondary" disabled={exporting} type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="runbtn" disabled={!hasFileName || exporting} type="submit">
            {exporting ? "Preparing…" : `Download ${format.toUpperCase()}`}
          </button>
        </div>
      </form>
    </Modal>
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

export function StatusPill({ children, tone, dot }: { children: ReactNode; tone: Tone; dot?: boolean }) {
  return (
    <span className={`pill tone-${tone}`}>
      {dot && <i className={`dot tone-${tone}`} />}
      {children}
    </span>
  );
}

export function Subhead({ children }: { children: ReactNode }) {
  return <h3 className="subhead">{children}</h3>;
}

export function LimitRow({ label, value, width, tone }: { label: string; value: string; width: number; tone: Tone }) {
  return (
    <div className="limit-row">
      <span>{label}</span>
      <div className="limit-track">
        <i className={`tone-${tone}`} style={{ width: `${Math.max(0, Math.min(100, width))}%` }} />
      </div>
      <strong>{value}</strong>
    </div>
  );
}
