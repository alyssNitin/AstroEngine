/**
 * src/components/auth/LoginForm.jsx — Email/password login form
 * ==============================================================
 * Handles the login form state, validation, submission, and error display.
 * On success calls `onSuccess(user)` — routing decisions are left to the parent.
 *
 * SOLID Notes
 * -----------
 * SRP : Manages login form state only — no routing, no token storage.
 * DIP : Uses useAuth hook (abstraction) rather than calling authApi directly.
 */
import React, { useState } from "react";
import Input from "../ui/Input.jsx";
import Button from "../ui/Button.jsx";
import ErrorMessage from "../ui/ErrorMessage.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { useLanguage } from "../../context/LanguageContext.jsx";

/**
 * @param {{
 *   onSuccess: (user: object) => void,
 *   onForgotPassword: () => void,
 * }} props
 */
export default function LoginForm({ onSuccess, onForgotPassword }) {
  const { login } = useAuth();
  const { t } = useLanguage();

  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState(null);
  const [loading,  setLoading]  = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (!email.trim()) return setError(t("emailRequired"));
    if (!password)     return setError(t("passwordRequired"));

    setLoading(true);
    try {
      const user = await login(email.trim(), password);
      onSuccess(user);
    } catch (err) {
      if (err.status === 403) {
        setError(t("unverifiedEmail"));
      } else if (err.status === 401) {
        setError(t("invalidCredentials"));
      } else {
        setError(err.detail ?? t("loginFailed"));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    /* B15: aria-label on form provides a landmark label (WCAG 1.3.6) */
    <form onSubmit={handleSubmit} noValidate aria-label="Sign in to your account">
      <ErrorMessage message={error} />

      <Input
        label={t("emailAddress")}
        id="login-email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />

      <Input
        label={t("password")}
        id="login-password"
        type="password"
        autoComplete="current-password"
        placeholder="••••••••"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      />

      {/* Forgot password link */}
      <div style={{ textAlign: "right", marginTop: "-8px", marginBottom: "16px" }}>
        <button
          type="button"
          onClick={onForgotPassword}
          style={{
            background: "none",
            border:     "none",
            color:      "var(--brand-purple-light)",
            fontSize:   "13px",
            cursor:     "pointer",
            padding:    0,
          }}
        >
          {t("forgotPassword")}
        </button>
      </div>

      <Button type="submit" fullWidth loading={loading}>
        {t("signIn")}
      </Button>
    </form>
  );
}
