/**
 * src/components/layout/AppHeader.jsx — Authenticated app header
 * ================================================================
 * Shows the brand logo, step progress bar, user name, wallet balance,
 * and a logout button.
 *
 * SOLID Notes
 * -----------
 * SRP : Pure layout/display — reads context, emits no side effects except logout.
 */
import React, { useState } from "react";
import { useAuth }     from "../../context/AuthContext.jsx";
import { useWallet }   from "../../context/WalletContext.jsx";
import { useSession, STEPS } from "../../context/SessionContext.jsx";
import { useLanguage } from "../../context/LanguageContext.jsx";
import Modal           from "../ui/Modal.jsx";
import Button          from "../ui/Button.jsx";
import WalletModal     from "../wallet/WalletModal.jsx";

/** Steps in reading progress bar order */
const PROGRESS_STEPS = [
  { key: STEPS.BIRTH,    label: "Birth Details" },
  { key: STEPS.CHART,    label: "Predictions"   },
  { key: STEPS.READING,  label: "Reading"       },
];

export default function AppHeader() {
  const { user, logout }                    = useAuth();
  const { balanceDisplay, region, refresh } = useWallet();
  const { step, goToStep, reset }           = useSession();
  const { lang, setLang, t, supportedLanguages } = useLanguage();
  const [showLogoutModal, setShowLogoutModal] = useState(false);
  const [showWallet,      setShowWallet]      = useState(false);

  function handleLogout() {
    logout();
    reset();
    setShowLogoutModal(false);
  }

  const currentStepIndex = PROGRESS_STEPS.findIndex((s) => s.key === step);

  return (
    <>
      {/* B15: WCAG 2.1 AA — skip-to-main link (2.4.1 Bypass Blocks) */}
      <a
        href="#main-content"
        style={{
          position:  "absolute",
          left:      "-9999px",
          top:       "auto",
          width:     "1px",
          height:    "1px",
          overflow:  "hidden",
        }}
        onFocus={(e) => {
          e.currentTarget.style.cssText =
            "position:fixed;top:8px;left:8px;z-index:9999;padding:8px 16px;" +
            "background:var(--brand-purple);color:#fff;border-radius:4px;" +
            "font-weight:600;text-decoration:none;width:auto;height:auto;overflow:visible;";
        }}
        onBlur={(e) => {
          e.currentTarget.style.cssText =
            "position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden;";
        }}
      >
        Skip to main content
      </a>

      <header
        role="banner"
        aria-label="Application header"
        style={{
          position:   "sticky",
          top:        0,
          zIndex:     100,
          background: "rgba(10,6,32,0.92)",
          backdropFilter: "blur(10px)",
          borderBottom: "1px solid var(--surface-border)",
          padding:    "0 24px",
        }}
      >
        <div
          style={{
            maxWidth:       "1100px",
            margin:         "0 auto",
            height:         "64px",
            display:        "flex",
            alignItems:     "center",
            justifyContent: "space-between",
            gap:            "16px",
          }}
        >
          {/* Brand — B15: use button for keyboard access (2.1.1) */}
          <button
            onClick={() => goToStep(STEPS.BIRTH)}
            aria-label="NarayanAstroReader — go to home"
            style={{
              cursor: "pointer", display: "flex", alignItems: "center", gap: "8px",
              background: "none", border: "none", padding: 0,
            }}
          >
            <span aria-hidden="true" style={{ fontSize: "22px" }}>🪐</span>
            <span
              style={{
                fontFamily: "var(--font-heading)",
                fontSize:   "16px",
                color:      "var(--brand-gold)",
                whiteSpace: "nowrap",
              }}
            >
              NarayanAstroReader
            </span>
          </button>

          {/* Progress bar — only show during reading flow */}
          {currentStepIndex >= 0 && (
            <nav
              aria-label="Reading progress"
              style={{
                display:   "flex",
                alignItems: "center",
                gap:       "4px",
                flex:      1,
                maxWidth:  "360px",
              }}
            >
              {/* B15: role="list" restores list semantics stripped by CSS flex (1.3.1) */}
              <div role="list" style={{ display: "contents" }}>
              {PROGRESS_STEPS.map((s, i) => {
                const done    = i < currentStepIndex;
                const active  = i === currentStepIndex;
                return (
                  <React.Fragment key={s.key}>
                    {/* B15: aria-current + aria-label describe step state (1.3.1, 4.1.2) */}
                    <div
                      role="listitem"
                      aria-current={active ? "step" : undefined}
                      aria-label={`${s.label}: ${done ? "completed" : active ? "current" : "upcoming"}`}
                      title={s.label}
                      style={{
                        width:        "24px",
                        height:       "24px",
                        borderRadius: "50%",
                        background:   done   ? "var(--brand-purple)" :
                                      active ? "var(--brand-purple-light)" :
                                               "var(--surface-elevated)",
                        border:       active ? "2px solid var(--brand-gold)" : "none",
                        display:      "flex",
                        alignItems:   "center",
                        justifyContent: "center",
                        fontSize:     "11px",
                        color:        done || active ? "#fff" : "var(--text-muted)",
                        flexShrink:   0,
                        transition:   "all var(--transition-base)",
                      }}
                    >
                      {done ? "✓" : i + 1}
                    </div>
                    {i < PROGRESS_STEPS.length - 1 && (
                      <div
                        style={{
                          flex:       1,
                          height:     "2px",
                          background: done ? "var(--brand-purple)" : "var(--surface-elevated)",
                          transition: "background var(--transition-base)",
                        }}
                      />
                    )}
                  </React.Fragment>
                );
              })}
              </div>{/* /role=list */}
            </nav>
          )}

          {/* Right side: language switcher + wallet + user */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>

            {/* Language switcher */}
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              aria-label="Change language"
              style={{
                background:   "var(--surface-elevated)",
                border:       "1px solid var(--surface-border)",
                borderRadius: "var(--radius-base)",
                color:        "var(--text-secondary)",
                fontSize:     "12px",
                padding:      "4px 8px",
                cursor:       "pointer",
              }}
            >
              {supportedLanguages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.nativeLabel}
                </option>
              ))}
            </select>

            {/* Wallet balance chip — B15: descriptive aria-label (4.1.2) */}
            <button
              onClick={() => setShowWallet(true)}
              aria-label={`Wallet balance: ${balanceDisplay}. Click to top up.`}
              title={t("wallet")}
              style={{
                background:   "var(--surface-elevated)",
                border:       "1px solid var(--surface-border)",
                borderRadius: "var(--radius-full)",
                padding:      "4px 12px",
                color:        "var(--brand-gold)",
                fontSize:     "13px",
                fontWeight:   "600",
                cursor:       "pointer",
                display:      "flex",
                alignItems:   "center",
                gap:          "4px",
              }}
            >
              💰 {balanceDisplay}
            </button>

            {/* User menu */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ color: "var(--text-secondary)", fontSize: "13px", maxWidth: "120px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {user?.name ?? user?.email}
              </span>
              <Button
                variant="ghost"
                onClick={() => setShowLogoutModal(true)}
                style={{ padding: "6px 12px", fontSize: "13px" }}
              >
                {t("signOut")}
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Wallet modal */}
      <WalletModal
        isOpen={showWallet}
        onClose={() => setShowWallet(false)}
        region={region ?? user?.region ?? "India"}
      />

      {/* Logout confirmation modal */}
      <Modal
        isOpen={showLogoutModal}
        onClose={() => setShowLogoutModal(false)}
        title={t("signOutConfirmTitle")}
        maxWidth={360}
      >
        <p style={{ color: "var(--text-secondary)", marginBottom: "20px" }}>
          {t("signOutConfirmBody")}
        </p>
        <div style={{ display: "flex", gap: "12px" }}>
          <Button variant="secondary" fullWidth onClick={() => setShowLogoutModal(false)}>
            {t("cancel")}
          </Button>
          <Button variant="danger" fullWidth onClick={handleLogout}>
            {t("signOut")}
          </Button>
        </div>
      </Modal>
    </>
  );
}
