export type Screen =
  | "overview"
  | "integrations"
  | "product"
  | "admin"
  | "review"
  | "results";

export type LeadWorkflowView = "inbox" | "this_week" | "shortlisted" | "contacted" | "dismissed" | "all";

export type LeadWorkflowCounts = Record<LeadWorkflowView, number>;

export type Tone = "blue" | "green" | "amber" | "red" | "gray";
