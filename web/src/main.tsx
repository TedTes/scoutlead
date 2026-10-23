import React from "react";
import ReactDOM from "react-dom/client";
import { RootApp } from "./auth/ClerkRoot";
import "./app/styles.css";
import "./app/motion.css";
import "leaflet/dist/leaflet.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RootApp />
  </React.StrictMode>,
);
