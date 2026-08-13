import { Box, Check, CircleDot, Grid2X2, MessageSquare, Plug, Table2 } from "lucide-react";
import type { Screen } from "../types/navigation";

export const screens: Array<{ id: Screen; label: string; icon: typeof Grid2X2; count?: string }> = [
  { id: "overview", label: "Overview", icon: Grid2X2 },
  { id: "product", label: "Product", icon: Box },
  { id: "campaigns", label: "Campaigns", icon: CircleDot, count: "4" },
  { id: "leads", label: "Leads", icon: Table2, count: "214" },
  { id: "approvals", label: "Approvals", icon: Check, count: "2" },
  { id: "conversations", label: "Conversations", icon: MessageSquare, count: "6" },
  { id: "connections", label: "Connections", icon: Plug },
];
