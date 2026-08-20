import { Box, Check, CircleDot, FileSearch, Grid2X2, Lightbulb, MessageSquare, Plug, Table2 } from "lucide-react";
import type { Screen } from "../types/navigation";

export type NavItem = { id: Screen; label: string; icon: typeof Grid2X2; count?: string };

export const navSections: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "This campaign",
    items: [
      { id: "overview", label: "Overview", icon: Grid2X2 },
      { id: "leads", label: "Leads", icon: Table2 },
      { id: "insights", label: "Insights", icon: Lightbulb },
      { id: "trace", label: "Trace", icon: FileSearch },
      { id: "approvals", label: "Approvals", icon: Check },
      { id: "conversations", label: "Conversations", icon: MessageSquare },
    ],
  },
  {
    title: "Manage",
    items: [
      { id: "product", label: "Products", icon: Box },
      { id: "campaigns", label: "Campaigns", icon: CircleDot },
      { id: "connections", label: "Connections", icon: Plug },
    ],
  },
];
