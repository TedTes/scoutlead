import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
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

export function useBusinessSelection(
  contacts: DiscoveryResult[] | null,
  canSelect?: (contact: DiscoveryResult) => boolean,
) {
  const [excludedIds, setExcludedIds] = useState<Set<string>>(() => new Set());
  const selectable = useMemo(() => canSelect ? contacts?.filter(canSelect) ?? [] : contacts ?? [], [contacts, canSelect]);
  const selectableIds = useMemo(() => new Set(selectable.map((contact) => contact.id)), [selectable]);
  const selected = useMemo(() => selectable.filter((contact) => !excludedIds.has(contact.id)), [selectable, excludedIds]);
  const selectedIds = useMemo(() => new Set(selected.map((contact) => contact.id)), [selected]);

  return {
    selectableIds,
    selected,
    selectedIds,
    setAll(checked: boolean) {
      setExcludedIds(checked ? new Set() : selectableIds);
    },
    toggle(id: string) {
      setExcludedIds((current) => {
        const next = new Set(current);
        if (!next.delete(id)) next.add(id);
        return next;
      });
    },
  };
}

export function BusinessSelectionList({ contacts, label, selection, disabled, status }: {
  contacts: DiscoveryResult[];
  label: string;
  selection: ReturnType<typeof useBusinessSelection>;
  disabled?: boolean;
  status?: (contact: DiscoveryResult) => string | undefined;
}) {
  const { selectedIds, selectableIds } = selection;
  const allChecked = selectableIds.size > 0 && selectedIds.size === selectableIds.size;

  return (
    <div className="bulk-review-selection">
      <div className="bulk-review-select-all">
        <label>
          <input
            type="checkbox"
            checked={allChecked}
            disabled={disabled || !selectableIds.size}
            ref={(input) => { if (input) input.indeterminate = selectedIds.size > 0 && !allChecked; }}
            onChange={(event) => selection.setAll(event.currentTarget.checked)}
          />
          Select all
        </label>
        <small aria-live="polite">{selectedIds.size} of {contacts.length} selected</small>
      </div>
      <ul className="bulk-review-list" aria-label={label} tabIndex={0}>
        {contacts.map((contact) => {
          const note = status?.(contact);
          return (
            <li key={contact.id}>
              <label>
                <input
                  type="checkbox"
                  aria-label={`Select ${contact.company_name}`}
                  checked={selectedIds.has(contact.id)}
                  disabled={disabled || !selectableIds.has(contact.id)}
                  onChange={() => selection.toggle(contact.id)}
                />
                <span>
                  <strong>{contact.company_name}</strong>
                  {contact.geography ? <small>{contact.geography}</small> : null}
                </span>
              </label>
              {note ? <small className="bulk-review-status">{note}</small> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function ExportBusinessesDialog({
  suggestedName,
  scope,
  loadBusinesses,
  onClose,
}: {
  suggestedName: string;
  scope: string;
  loadBusinesses: () => Promise<DiscoveryResult[]>;
  onClose: () => void;
}) {
  const { showToast } = useToast();
  const [fileName, setFileName] = useState(suggestedName);
  const [format, setFormat] = useState<BusinessExportFormat>("csv");
  const [businesses, setBusinesses] = useState<DiscoveryResult[] | null>(null);
  const [error, setError] = useState("");
  const selection = useBusinessSelection(businesses);
  const hasFileName = Boolean(baseExportFileName(fileName));
  const downloadName = normalizeExportFileName(fileName, format);
  const canDownload = hasFileName && selection.selected.length > 0;

  useEffect(() => {
    let active = true;
    void loadBusinesses().then((rows) => {
      if (active) setBusinesses(rows);
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : "Could not load businesses for export.");
    });
    return () => { active = false; };
  }, [loadBusinesses]);

  const download = () => {
    if (!canDownload) return;
    try {
      exportBusinesses(selection.selected, downloadName, format);
      showToast({ title: "Export downloaded", message: downloadName, tone: "green" });
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not download the export.");
    }
  };

  return (
    <Modal title="Export businesses" className="bulk-review-modal" onClose={onClose}>
      <form
        className="export-contacts-form"
        onSubmit={(event) => {
          event.preventDefault();
          download();
        }}
      >
        <p>{scope}</p>
        {businesses?.length ? <BusinessSelectionList contacts={businesses} label={scope} selection={selection} />
          : businesses ? <p>No businesses to export in this view.</p>
          : !error ? <div className="loading-indicator" aria-live="polite"><span className="sl-spin" aria-hidden="true" /> Loading businesses…</div> : null}
        <label className="field">
          <span>Format</span>
          <select value={format} onChange={(event) => setFormat(event.target.value === "json" ? "json" : "csv")}>
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
        </label>
        <label className="field">
          <span>File name</span>
          <input
            autoFocus
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
          <button className="secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="runbtn" disabled={!canDownload} type="submit">
            Download {format.toUpperCase()}
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
