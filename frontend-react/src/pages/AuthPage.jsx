/**
 * src/pages/AuthPage.jsx — Authentication page (Login / Register / ForgotPassword)
 * ==================================================================================
 * Orchestrates auth tab switching and transitions.
 * After a successful login it navigates to the reading flow.
 *
 * SOLID Notes
 * -----------
 * SRP : Owns only auth-page layout and tab switching.
 * DIP : Uses context hooks and form components — not raw API calls.
 */
import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import Card from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import ErrorMessage from "../components/ui/ErrorMessage.jsx";
import LoginForm from "../components/auth/LoginForm.jsx";
import RegisterForm from "../components/auth/RegisterForm.jsx";
import ForgotPasswordForm from "../components/auth/ForgotPasswordForm.jsx";

import { useAuth } from "../context/AuthContext.jsx";
import { verifyEmail } from "../api/authApi.js";

/** Auth tabs */
const TABS = { LOGIN: "login", REGISTER: "register", FORGOT: "forgot" };

export default function AuthPage() {
  const navigate       = useNavigate();
  const [params]       = useSearchParams();
  const { isAuthenticated } = useAuth();

  const [tab,     setTab]     = useState(TABS.LOGIN);
  const [verMsg,  setVerMsg]  = useState(null);   // verification feedback
  const [verType, setVerType] = useState("info");

  // ── Already logged in — bounce to reading ──────────────────────────────────
  useEffect(() => {
    if (isAuthenticated) navigate("/reading", { replace: true });
  }, [isAuthenticated, navigate]);

  // ── Handle email-verification token in URL ────────────────────────────────
  useEffect(() => {
    const token = params.get("token");
    if (!token) return;

    verifyEmail(token)
      .then(() => {
        setVerMsg("✅ Email verified! You can now sign in.");
        setVerType("success");
      })
      .catch((err) => {
        setVerMsg(err.detail ?? "Verification link is invalid or expired.");
        setVerType("error");
      });
  }, [params]);

  // ── Handle password-reset token in URL ───────────────────────────────────
  useEffect(() => {
    const resetToken = params.get("reset_token") ?? params.get("token");
    const flow       = params.get("flow");
    if (flow === "reset" && resetToken) {
      navigate(`/reset-password?token=${resetToken}`, { replace: true });
    }
  }, [params, navigate]);

  function handleLoginSuccess() {
    navigate("/reading", { replace: true });
  }

  return (
    /* B15: <main> landmark + id for skip-link target (WCAG 2.4.1) */
    <main
      id="main-content"
      aria-label="Authentication"
      style={{
        minHeight:      "100vh",
        display:        "flex",
        alignItems:     "center",
        justifyContent: "center",
        padding:        "24px 16px",
      }}
    >
      <div style={{ width: "100%", maxWidth: "440px" }}>
        {/* Brand header */}
        <div style={{ textAlign: "center", marginBottom: "32px" }}>
          <div style={{ fontSize: "48px", marginBottom: "8px" }}>🪐</div>
          <h1
            style={{
              fontFamily:  "var(--font-heading)",
              fontSize:    "28px",
              color:       "var(--brand-gold)",
              marginBottom: "4px",
            }}
          >
            NarayanAstroReader
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
            AI-powered Vedic astrology readings
          </p>
        </div>

        {/* Verification feedback */}
        {verMsg && <ErrorMessage message={verMsg} type={verType} />}

        <Card glow>
          {/* Tab switcher — B15: role="tablist"/tab/tabpanel pattern (WCAG 4.1.2) */}
          {tab !== TABS.FORGOT && (
            <div
              role="tablist"
              aria-label="Authentication options"
              style={{
                display:       "flex",
                borderBottom:  "1px solid var(--surface-border)",
                marginBottom:  "24px",
              }}
            >
              {[TABS.LOGIN, TABS.REGISTER].map((t) => (
                <button
                  key={t}
                  role="tab"
                  aria-selected={tab === t ? "true" : "false"}
                  aria-controls={`tabpanel-${t}`}
                  id={`tab-${t}`}
                  onClick={() => setTab(t)}
                  style={{
                    flex:         1,
                    padding:      "10px",
                    background:   "none",
                    border:       "none",
                    borderBottom: tab === t ? "2px solid var(--brand-purple)" : "2px solid transparent",
                    color:        tab === t ? "var(--text-primary)" : "var(--text-muted)",
                    fontWeight:   tab === t ? "600" : "400",
                    fontSize:     "15px",
                    cursor:       "pointer",
                    transition:   "all var(--transition-fast)",
                    textTransform: "capitalize",
                    marginBottom: "-1px",
                  }}
                >
                  {t === TABS.LOGIN ? "Sign In" : "Create Account"}
                </button>
              ))}
            </div>
          )}

          {/* Tab content */}
          {tab === TABS.LOGIN    && (
            <LoginForm
              onSuccess={handleLoginSuccess}
              onForgotPassword={() => setTab(TABS.FORGOT)}
            />
          )}
          {tab === TABS.REGISTER && (
            <RegisterForm onSuccess={() => setTab(TABS.LOGIN)} />
          )}
          {tab === TABS.FORGOT   && (
            <ForgotPasswordForm onBack={() => setTab(TABS.LOGIN)} />
          )}
        </Card>

        {/* Footer note */}
        <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "12px", marginTop: "20px" }}>
          🔒 Your birth data is encrypted and never shared.
        </p>
      </div>
    </main>
  );
}
