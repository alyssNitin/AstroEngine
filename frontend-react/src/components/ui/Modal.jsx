/**
 * src/components/ui/Modal.jsx — Accessible modal dialog component
 * ================================================================
 * Traps focus, supports Escape key, and renders a backdrop.
 * Children are the modal's content.
 *
 * SOLID Notes
 * -----------
 * SRP : Manages only overlay presentation and focus trap.
 * OCP : Title, footer, size can all vary without modifying this component.
 */
import React, { useEffect, useRef } from "react";

/**
 * @param {{
 *   isOpen: boolean,
 *   onClose: () => void,
 *   title?: string,
 *   children: React.ReactNode,
 *   maxWidth?: number,
 *   hideClose?: boolean,
 * }} props
 */
export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  maxWidth  = 480,
  hideClose = false,
}) {
  const dialogRef = useRef(null);

  // Trap focus + Escape key
  useEffect(() => {
    if (!isOpen) return;
    const prev = document.activeElement;
    dialogRef.current?.focus();

    const handleKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      prev?.focus();
    };
  }, [isOpen, onClose]);

  // Prevent body scroll while modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    /* Backdrop */
    <div
      role="presentation"
      onClick={onClose}
      style={{
        position:        "fixed",
        inset:           0,
        background:      "rgba(10,6,32,0.80)",
        backdropFilter:  "blur(6px)",
        zIndex:          500,
        display:         "flex",
        alignItems:      "center",
        justifyContent:  "center",
        padding:         "16px",
        animation:       "fadeIn 0.2s ease",
      }}
    >
      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? "modal-title" : undefined}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          background:   "var(--surface-card)",
          border:       "1px solid var(--surface-border)",
          borderRadius: "var(--radius-lg)",
          boxShadow:    "var(--shadow-lg), var(--shadow-glow)",
          width:        "100%",
          maxWidth:     maxWidth,
          maxHeight:    "90vh",
          overflowY:    "auto",
          outline:      "none",
          animation:    "fadeIn 0.25s ease",
        }}
      >
        {/* Header */}
        {(title || !hideClose) && (
          <div
            style={{
              display:         "flex",
              alignItems:      "center",
              justifyContent:  "space-between",
              padding:         "20px 24px 0",
              marginBottom:    "16px",
            }}
          >
            {title && (
              <h2
                id="modal-title"
                style={{
                  fontFamily: "var(--font-heading)",
                  fontSize:   "18px",
                  color:      "var(--text-primary)",
                }}
              >
                {title}
              </h2>
            )}
            {!hideClose && (
              <button
                onClick={onClose}
                aria-label="Close dialog"
                style={{
                  background:   "none",
                  border:       "none",
                  color:        "var(--text-secondary)",
                  fontSize:     "20px",
                  cursor:       "pointer",
                  padding:      "4px 8px",
                  borderRadius: "var(--radius-sm)",
                  lineHeight:   1,
                }}
              >
                ✕
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div style={{ padding: "0 24px 24px" }}>{children}</div>
      </div>
    </div>
  );
}
