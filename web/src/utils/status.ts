import type { Tone } from "../types/navigation";

export function statusTone(status: string): Tone {
  const value = status.toLowerCase();
  if (["running", "researching"].includes(value)) return "blue";
  if (["active", "connected", "qualified", "completed", "interested", "meeting booked"].includes(value)) {
    return "green";
  }
  if (["paused", "pending", "queued", "waiting", "review", "not now", "degraded"].includes(value)) return "amber";
  if (["objection", "disqualified", "failed", "cancelled"].includes(value)) return "red";
  return "gray";
}

export function scoreTone(score: number): Tone {
  if (score >= 80) return "green";
  if (score >= 60) return "amber";
  return "gray";
}
