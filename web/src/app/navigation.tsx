import { Box, Check, Grid2X2, Plug, Table2 } from "lucide-react";
import type { Screen } from "../types/navigation";

export type NavItem = { id: Screen; label: string; icon: typeof Grid2X2; count?: string };

export const navSections: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "Discovery",
    items: [
      { id: "overview", label: "Overview", icon: Grid2X2 },
      { id: "results", label: "Results", icon: Table2 },
      { id: "approvals", label: "Approvals", icon: Check },
    ],
  },
  {
    title: "Manage",
    items: [
      { id: "product", label: "Products", icon: Box },
      { id: "connections", label: "Connections", icon: Plug },
    ],
  },
];
