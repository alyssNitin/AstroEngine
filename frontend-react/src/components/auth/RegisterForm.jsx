/**
 * src/components/auth/RegisterForm.jsx — New account registration form
 * ======================================================================
 * Collects name, email, password (+ confirm), region.
 * On success shows a "check your email" message.
 *
 * SOLID Notes
 * -----------
 * SRP : Manages registration form state only.
 * DIP : Calls authApi.register via the service abstraction.
 */
import React, { useState } from "react";
import Input, { Select } from "../ui/Input.jsx";
import Button from "../ui/Button.jsx";
import ErrorMessage from "../ui/ErrorMessage.jsx";
import * as authApi from "../../api/authApi.js";
import { useLanguage } from "../../context/LanguageContext.jsx";

// Values MUST match what the backend register endpoint accepts exactly.
// Backend code: region = req.region if req.region in ("India", "International") else "India"
const REGION_OPTIONS = [
  { value: "India",         label: "🇮🇳 India (₹ INR)" },
  { value: "International", label: "🌍 International ($ USD)" },
];

/**
 * @param {{
 *   onSuccess: () => void,   // called after successful registration
 * }} props
 */
export default function RegisterForm({ onSuccess }) {
  const { t } = useLanguage();
  const [form, setForm] = useState({
    name:     "",
    email:    "",
    password: "",
    confirm:  "",
    region:   "India",   // default to India — matches backend accepted value
  });
  const [error,   setError]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [done,    setDone]    = useState(false);

  const set = (field) => (e) => setForm((p) => ({ ...p, [field]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    // Validation
    if (!form.name.trim())              return setError(t("nameRequired"));
    if (!form.email.trim())             return setError(t("emailRequired"));
    if (form.password.length < 8)       return setError(t("passwordTooShort"));
    if (form.password !== form.confirm) return setError(t("passwordMismatch"));

    setLoading(true);
    try {
      await authApi.register({
        name:     form.name.trim(),
        email:    form.email.trim().toLowerCase(),
        password: form.password,
        region:   form.region,
      });
      setDone(true);
      onSuccess?.();
    } catch (err) {
      if (err.status === 409) {
        setError(t("emailTaken"));
      } else {
        setError(err.detail ?? t("registerFailed"));
      }
    } finally {
      setLoading(false);
    }
  }

  // ── Post-registration success message ──────────────────────────────────────
  if (done) {
    return (
      <div style={{ textAlign: "center", padding: "24px 0" }}>
        <div style={{ fontSize: "48px", marginBottom: "16px" }}>📧</div>
        <h3 style={{ color: "var(--color-success)", marginBottom: "8px" }}>
          Account created!
        </h3>
        <p style={{ color: "var(--text-secondary)", lineHeight: "1.6" }}>
          We've sent a verification link to <strong>{form.email}</strong>.
          <br />
          Please check your inbox (and spam folder) and click the link to activate your account.
        </p>
        <ResendButton email={form.email} />
      </div>
    );
  }

  return (
    /* B15: aria-label on form for screen reader landmark (WCAG 1.3.6) */
    <form onSubmit={handleSubmit} noValidate aria-label="Create a new account">
      <ErrorMessage message={error} />

      <Input
        label={t("fullName")}
        id="reg-name"
        type="text"
        autoComplete="name"
        placeholder="Arjuna Sharma"
        value={form.name}
        onChange={set("name")}
        required
      />

      <Input
        label={t("emailAddress")}
        id="reg-email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        value={form.email}
        onChange={set("email")}
        required
      />

      <Select
        label={t("regionCurrency")}
        id="reg-region"
        options={REGION_OPTIONS}
        value={form.region}
        onChange={set("region")}
      />

      <Input
        label={t("password")}
        id="reg-password"
        type="password"
        autoComplete="new-password"
        placeholder="At least 8 characters"
        value={form.password}
        onChange={set("password")}
        required
      />

      <Input
        label={t("confirmPassword")}
        id="reg-confirm"
        type="password"
        autoComplete="new-password"
        placeholder="••••••••"
        value={form.confirm}
        onChange={set("confirm")}
        required
      />

      <Button type="submit" fullWidth loading={loading}>
        {t("createAccount")}
      </Button>

      <p style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "12px", textAlign: "center" }}>
        By creating an account you agree to our terms of service.
      </p>
    </form>
  );
}

// ── ResendButton sub-component ────────────────────────────────────────────────
function ResendButton({ email }) {
  const [sent,    setSent]    = useState(false);
  const [loading, setLoading] = useState(false);

  async function resend() {
    setLoading(true);
    try {
      await authApi.resendVerification(email);
      setSent(true);
    } catch {
      // silently ignore — user can try again
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <p style={{ color: "var(--color-success)", marginTop: "16px", fontSize: "13px" }}>
        ✅ Verification email resent!
      </p>
    );
  }

  return (
    <Button
      variant="ghost"
      onClick={resend}
      loading={loading}
      style={{ marginTop: "16px", fontSize: "13px" }}
    >
      Didn't receive it? Resend
    </Button>
  );
}
