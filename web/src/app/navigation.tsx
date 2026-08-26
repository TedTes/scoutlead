import { Box, Plug, Search, Table2 } from "lucide-react";
import type { Screen } from "../types/navigation";

export type NavItem = { id: Screen; label: string; icon: typeof Search; count?: string };

export const navSections: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "Discovery",
    items: [
      { id: "overview", label: "Find", icon: Search },
      { id: "results", label: "Contacts", icon: Table2 },
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
