import type { Tone } from "../types/navigation";

export function statusTone(status: string): Tone {
  const value = status.toLowerCase();
  if (["running", "researching", "outreach_drafted", "sent"].includes(value)) return "blue";
  if (
    ["active", "connected", "qualified", "completed", "interested", "meeting booked", "approved", "responded"].includes(
      value,
    )
  ) {
    return "green";
  }
  if (
    ["paused", "pending", "queued", "waiting", "review", "not now", "degraded", "awaiting_approval"].includes(value)
  ) {
    return "amber";
  }
  if (["objection", "disqualified", "failed", "cancelled"].includes(value)) return "red";
  return "gray";
}

export function scoreTone(score: number): Tone {
  const normalized = score <= 10 ? score * 10 : score;
  if (normalized >= 80) return "green";
  if (normalized >= 60) return "amber";
  return "gray";
}
