/**
 * src/components/ui/Button.jsx — Reusable button component
 * ==========================================================
 * Supports: primary | secondary | ghost | danger variants,
 * full-width, loading state with spinner, and disabled state.
 *
 * SOLID Notes
 * -----------
 * SRP : Renders a styled button only — no business logic.
 * OCP : New variants can be added via the `variant` prop without changing
 *       existing call-sites.
 */
import React from "react";

/** @type {Record<string, React.CSSProperties>} */
const VARIANT_STYLES = {
  primary: {
    background: "var(--brand-purple)",
    color:      "#fff",
    border:     "none",
  },
  secondary: {
    background: "transparent",
    color:      "var(--brand-purple-light)",
    border:     "1.5px solid var(--brand-purple)",
  },
  ghost: {
    background: "transparent",
    color:      "var(--text-secondary)",
    border:     "none",
  },
  danger: {
    background: "var(--color-error)",
    color:      "#fff",
    border:     "none",
  },
  gold: {
    background: "var(--brand-gold)",
    color:      "#1a0e4a",
    border:     "none",
    fontWeight: "700",
  },
};

const BASE_STYLE = {
  display:        "inline-flex",
  alignItems:     "center",
  justifyContent: "center",
  gap:            "8px",
  padding:        "10px 24px",
  borderRadius:   "var(--radius-md)",
  fontSize:       "15px",
  fontWeight:     "600",
  cursor:         "pointer",
  transition:     "opacity var(--transition-fast), transform var(--transition-fast)",
  whiteSpace:     "nowrap",
  userSelect:     "none",
  letterSpacing:  "0.02em",
};

const DISABLED_STYLE = {
  opacity: 0.5,
  cursor:  "not-allowed",
};

const FULL_WIDTH_STYLE = { width: "100%" };

/**
 * @param {{
 *   children: React.ReactNode,
 *   variant?: "primary"|"secondary"|"ghost"|"danger"|"gold",
 *   fullWidth?: boolean,
 *   loading?: boolean,
 *   disabled?: boolean,
 *   onClick?: Function,
 *   type?: "button"|"submit"|"reset",
 *   style?: React.CSSProperties,
 *   className?: string,
 * }} props
 */
export default function Button({
  children,
  variant   = "primary",
  fullWidth = false,
  loading   = false,
  disabled  = false,
  onClick,
  type    = "button",
  style   = {},
  className = "",
  ...rest
}) {
  const isDisabled = disabled || loading;

  const computedStyle = {
    ...BASE_STYLE,
    ...(VARIANT_STYLES[variant] ?? VARIANT_STYLES.primary),
    ...(isDisabled ? DISABLED_STYLE : {}),
    ...(fullWidth   ? FULL_WIDTH_STYLE : {}),
    ...style,
  };

  return (
    <button
      type={type}
      disabled={isDisabled}
      onClick={isDisabled ? undefined : onClick}
      style={computedStyle}
      className={className}
      /* B15: WCAG 2.1 AA — aria-busy signals in-progress to screen readers;
         aria-disabled mirrors disabled for AT that checks aria attributes */
      aria-busy={loading ? "true" : undefined}
      aria-disabled={isDisabled ? "true" : undefined}
      {...rest}
    >
      {loading && (
        <>
          <Spinner size={16} color="currentColor" />
          {/* B15: visually-hidden live region announces loading to screen readers */}
          <span
            aria-live="polite"
            style={{
              position: "absolute", width: "1px", height: "1px",
              padding: 0, margin: "-1px", overflow: "hidden",
              clip: "rect(0,0,0,0)", whiteSpace: "nowrap", border: 0,
            }}
          >
            Loading…
          </span>
        </>
      )}
      {children}
    </button>
  );
}

// ── Inline Spinner ────────────────────────────────────────────────────────────
function Spinner({ size = 16, color = "#fff" }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display:      "inline-block",
        width:        size,
        height:       size,
        border:       `2px solid transparent`,
        borderTop:    `2px solid ${color}`,
        borderRadius: "50%",
        animation:    "spin 0.75s linear infinite",
      }}
    />
  );
}
