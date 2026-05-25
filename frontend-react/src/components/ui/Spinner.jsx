/**
 * src/components/ui/Spinner.jsx — Loading spinner component
 * ===========================================================
 * A full-screen or inline cosmic loading indicator.
 *
 * Props:
 *   fullScreen  : centres the spinner on the whole viewport
 *   size        : diameter in px (default 48)
 *   message     : optional text beneath the spinner
 */
import React from "react";

/**
 * @param {{
 *   fullScreen?: boolean,
 *   size?: number,
 *   message?: string,
 *   color?: string,
 * }} props
 */
export default function Spinner({
  fullScreen = false,
  size       = 48,
  message    = "",
  color      = "var(--brand-purple-light)",
}) {
  const spinner = (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
      {/* Outer ring */}
      <div
        aria-label="Loading…"
        role="status"
        style={{
          width:        size,
          height:       size,
          borderRadius: "50%",
          border:       `${Math.max(2, size / 12)}px solid rgba(255,255,255,0.08)`,
          borderTop:    `${Math.max(2, size / 12)}px solid ${color}`,
          animation:    "spin 0.9s linear infinite",
        }}
      />
      {message && (
        <p style={{ color: "var(--text-secondary)", fontSize: "14px", textAlign: "center" }}>
          {message}
        </p>
      )}
    </div>
  );

  if (!fullScreen) return spinner;

  return (
    <div
      style={{
        position:       "fixed",
        inset:          0,
        display:        "flex",
        alignItems:     "center",
        justifyContent: "center",
        background:     "rgba(10,6,32,0.85)",
        zIndex:         1000,
        backdropFilter: "blur(4px)",
      }}
    >
      {spinner}
    </div>
  );
}
