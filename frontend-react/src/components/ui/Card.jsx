/**
 * src/components/ui/Card.jsx — Surface card component
 * =====================================================
 * Provides the dark-purple glass-morphism card used throughout the app.
 *
 * SOLID Notes
 * -----------
 * SRP : Pure presentational component — wraps children in a styled surface.
 */
import React from "react";

/**
 * @param {{
 *   children: React.ReactNode,
 *   glow?: boolean,      // show purple glow shadow
 *   padded?: boolean,    // default true — apply standard padding
 *   style?: object,
 *   className?: string,
 *   onClick?: Function,
 * }} props
 */
export default function Card({
  children,
  glow     = false,
  padded   = true,
  style    = {},
  className = "",
  onClick,
}) {
  return (
    <div
      onClick={onClick}
      className={`animate-fade-in ${className}`}
      style={{
        background:   "var(--surface-card)",
        border:       "1px solid var(--surface-border)",
        borderRadius: "var(--radius-lg)",
        boxShadow:    glow
          ? "var(--shadow-md), var(--shadow-glow)"
          : "var(--shadow-md)",
        padding:      padded ? "24px" : undefined,
        cursor:       onClick ? "pointer" : undefined,
        transition:   onClick ? "box-shadow var(--transition-base)" : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ── Card.Header convenience sub-component ────────────────────────────────────
Card.Header = function CardHeader({ children, style = {} }) {
  return (
    <div
      style={{
        borderBottom: "1px solid var(--surface-border)",
        paddingBottom: "16px",
        marginBottom:  "16px",
        ...style,
      }}
    >
      {children}
    </div>
  );
};
