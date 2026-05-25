/**
 * src/components/auth/ForgotPasswordForm.jsx — Password reset request form
 * ==========================================================================
 * Sends a reset link to the user's email.
 * On success, shows confirmation message.
 */
import React, { useState } from "react";
import Input from "../ui/Input.jsx";
import Button from "../ui/Button.jsx";
import ErrorMessage from "../ui/ErrorMessage.jsx";
import { forgotPassword } from "../../api/authApi.js";

/**
 * @param {{ onBack: () => void }} props
 */
export default function ForgotPasswordForm({ onBack }) {
  const [email,   setEmail]   = useState("");
  const [error,   setError]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [sent,    setSent]    = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!email.trim()) return setError("Please enter your email address.");
    setLoading(true);
    try {
      await forgotPassword(email.trim().toLowerCase());
      setSent(true);
    } catch (err) {
      setError(err.detail ?? "Failed to send reset link. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <div style={{ textAlign: "center", padding: "16px 0" }}>
        <div style={{ fontSize: "40px", marginBottom: "12px" }}>📬</div>
        <h3 style={{ color: "var(--color-success)", marginBottom: "8px" }}>
          Reset link sent!
        </h3>
        <p style={{ color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.6" }}>
          Check your inbox at <strong>{email}</strong> for the password reset link.
          <br />
          The link expires in 1 hour.
        </p>
        <Button variant="ghost" onClick={onBack} style={{ marginTop: "20px" }}>
          ← Back to sign in
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <p style={{ color: "var(--text-secondary)", fontSize: "14px", marginBottom: "20px" }}>
        Enter the email address on your account and we'll send you a link to reset your password.
      </p>

      <ErrorMessage message={error} />

      <Input
        label="Email address"
        id="forgot-email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />

      <Button type="submit" fullWidth loading={loading}>
        Send Reset Link
      </Button>

      <Button
        type="button"
        variant="ghost"
        fullWidth
        onClick={onBack}
        style={{ marginTop: "8px" }}
      >
        ← Back to sign in
      </Button>
    </form>
  );
}
