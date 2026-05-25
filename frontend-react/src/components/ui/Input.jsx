/**
 * src/components/ui/Input.jsx — Labelled text input component
 * =============================================================
 * Renders a styled <label> + <input> (or <select> / <textarea>) pair.
 * Supports error states, helper text, and icon addornments.
 *
 * SOLID Notes
 * -----------
 * SRP : Renders a form field only — no validation logic.
 */
import React, { forwardRef } from "react";

const FIELD_STYLE = {
  width:           "100%",
  padding:         "10px 14px",
  background:      "rgba(255,255,255,0.06)",
  border:          "1.5px solid var(--surface-border)",
  borderRadius:    "var(--radius-md)",
  color:           "var(--text-primary)",
  fontSize:        "15px",
  outline:         "none",
  transition:      "border-color var(--transition-fast)",
  boxSizing:       "border-box",
};

const LABEL_STYLE = {
  display:    "block",
  marginBottom: "6px",
  fontSize:   "13px",
  fontWeight: "500",
  color:      "var(--text-secondary)",
};

const ERROR_STYLE = {
  fontSize:   "12px",
  color:      "var(--color-error)",
  marginTop:  "4px",
};

const HELPER_STYLE = {
  fontSize:   "12px",
  color:      "var(--text-muted)",
  marginTop:  "4px",
};

/**
 * @param {{
 *   label?: string,
 *   id?: string,
 *   error?: string,
 *   helper?: string,
 *   as?: "input"|"select"|"textarea",
 *   children?: React.ReactNode,   // for <select> options
 *   [key: string]: any,
 * }} props
 */
const Input = forwardRef(function Input(
  {
    label,
    id,
    error,
    helper,
    as: Tag = "input",
    children,
    style = {},
    required,
    ...rest
  },
  ref,
) {
  // B15: WCAG 2.1 AA — aria-describedby links input to its error/helper text
  const errorId  = id ? `${id}-error`  : undefined;
  const helperId = id ? `${id}-helper` : undefined;
  const describedBy = [
    error  && errorId,
    !error && helper && helperId,
  ].filter(Boolean).join(" ") || undefined;

  const fieldStyle = {
    ...FIELD_STYLE,
    ...(error ? { borderColor: "var(--color-error)" } : {}),
    ...(Tag === "textarea" ? { minHeight: "90px", resize: "vertical" } : {}),
    ...style,
  };

  return (
    <div style={{ marginBottom: "16px" }}>
      {label && (
        <label htmlFor={id} style={LABEL_STYLE}>
          {label}
          {/* B15: visually flag required fields */}
          {required && (
            <span aria-hidden="true" style={{ color: "var(--color-error)", marginLeft: "3px" }}>*</span>
          )}
        </label>
      )}

      <Tag
        id={id}
        ref={ref}
        style={fieldStyle}
        aria-invalid={error ? "true" : undefined}
        aria-required={required ? "true" : undefined}
        aria-describedby={describedBy}
        required={required}
        {...rest}
      >
        {children}
      </Tag>

      {/* B15: role="alert" + id for aria-describedby linkage; aria-live for dynamic errors */}
      {error  && <p id={errorId}  style={ERROR_STYLE}  role="alert" aria-live="polite">{error}</p>}
      {helper && !error && <p id={helperId} style={HELPER_STYLE}>{helper}</p>}
    </div>
  );
});

export default Input;

// ── Select convenience wrapper ────────────────────────────────────────────────

/**
 * Styled <select> using the same design as Input.
 * @param {{ label: string, id: string, options: Array<{value,label}>, error?: string, [key:string]:any }} props
 */
export function Select({ label, id, options = [], error, ...rest }) {
  return (
    <Input as="select" label={label} id={id} error={error} {...rest}>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value} style={{ background: "#12083a" }}>
          {opt.label}
        </option>
      ))}
    </Input>
  );
}
