import type { Tone } from "../types/navigation";

export function statusTone(status: string): Tone {
  const value = status.toLowerCase();
  if (["running", "researching", "discovered", "outreach_drafted", "sent"].includes(value)) return "blue";
  if (
    [
      "active",
      "connected",
      "qualified",
      "completed",
      "interested",
      "meeting booked",
      "approved",
      "responded",
      "strong",
    ].includes(value)
  ) {
    return "green";
  }
  if (
    [
      "paused",
      "pending",
      "queued",
      "waiting",
      "review",
      "researched",
      "not now",
      "degraded",
      "awaiting_approval",
      "mixed",
      "weak",
      "insufficient_data",
    ].includes(value)
  ) {
    return "amber";
  }
  if (["objection", "failed", "cancelled", "invalid"].includes(value)) return "red";
  return "gray";
}

export function scoreTone(score: number): Tone {
  const normalized = score <= 10 ? score * 10 : score;
  if (normalized >= 80) return "green";
  if (normalized >= 60) return "amber";
  return "gray";
}

const RESULT_STAGE_LABELS: Record<string, string> = {
  discovered: "Researching",
  researching: "Researching",
  researched: "Review",
  qualified: "Qualified",
  disqualified: "Disqualified",
  outreach_drafted: "Drafting outreach",
  awaiting_approval: "Awaiting approval",
  approved: "Approved",
  sent: "Sent",
  responded: "Responded",
  archived: "Archived",
};

export function resultStageLabel(status: string): string {
  return RESULT_STAGE_LABELS[status.toLowerCase()] ?? status.replace(/_/g, " ");
}

export function isLiveResultStage(status: string): boolean {
  return ["discovered", "researching", "outreach_drafted", "sent"].includes(status.toLowerCase());
}
