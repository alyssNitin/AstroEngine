/**
 * src/main.jsx — Application entry point
 * =========================================
 * Mounts the React app to the #root DOM node.
 * Imports global CSS before rendering so styles are available immediately.
 *
 * StrictMode is enabled in development to help catch potential issues.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
