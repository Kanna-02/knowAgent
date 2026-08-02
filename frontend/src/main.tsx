import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./app/App";
import { applyDesignTokenVariables } from "./shared/designTokens";
import "./styles.css";

applyDesignTokenVariables();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
