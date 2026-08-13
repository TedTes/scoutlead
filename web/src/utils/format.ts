export function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(value));
}

export function formatPercent(value?: number) {
  return `${Math.round((value ?? 0) * 100)}%`;
}
