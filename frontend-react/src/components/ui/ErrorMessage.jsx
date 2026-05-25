/**
 * src/components/ui/ErrorMessage.jsx — Inline error / success alert
 * ==================================================================
 * Renders a coloured alert banner. Used inside forms and pages.
 *
 * SOLID Notes
 * -----------
 * SRP : Pure presentation — just shows a message with a colour.
 */
import React from "react";

const TYPE_STYLES = {
  error: {
    background:  "rgba(248,113,113,0.12)",
    border:      "1px solid rgba(248,113,113,0.35)",
    color:       "var(--color-error)",
    icon:        "⚠️",
  },
  success: {
    background:  "rgba(74,222,128,0.12)",
    border:      "1px solid rgba(74,222,128,0.35)",
    color:       "var(--color-success)",
    icon:        "✅",
  },
  info: {
    background:  "rgba(96,165,250,0.12)",
    border:      "1px solid rgba(96,165,250,0.35)",
    color:       "var(--color-info)",
    icon:        "ℹ️",
  },
  warning: {
    background:  "rgba(251,146,60,0.12)",
    border:      "1px solid rgba(251,146,60,0.35)",
    color:       "var(--color-warning)",
    icon:        "⚠️",
  },
};

/**
 * @param {{
 *   message: string | null | undefined,
 *   type?: "error" | "success" | "info" | "warning",
 *   style?: object,
 * }} props
 */
export default function ErrorMessage({ message, type = "error", style = {} }) {
  if (!message) return null;

  const { background, border, color, icon } = TYPE_STYLES[type] ?? TYPE_STYLES.error;

  // B15: WCAG 4.1.3 — errors use assertive (immediate), info/success use polite
  const liveValue = type === "error" ? "assertive" : "polite";

  return (
    <div
      role="alert"
      aria-live={liveValue}
      aria-atomic="true"
      style={{
        display:      "flex",
        alignItems:   "flex-start",
        gap:          "8px",
        padding:      "10px 14px",
        borderRadius: "var(--radius-md)",
        fontSize:     "14px",
        marginBottom: "12px",
        animation:    "fadeIn 0.2s ease",
        background,
        border,
        color,
        ...style,
      }}
    >
      <span aria-hidden="true">{icon}</span>
      <span>{message}</span>
    </div>
  );
}
