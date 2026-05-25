/**
 * src/pages/ResetPasswordPage.jsx — Password reset completion page
 * =================================================================
 * Reached from the link in the password-reset email (?token=...).
 * Collects new password and submits it.
 */
import React, { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Card         from "../components/ui/Card.jsx";
import Input        from "../components/ui/Input.jsx";
import Button       from "../components/ui/Button.jsx";
import ErrorMessage from "../components/ui/ErrorMessage.jsx";
import { resetPassword } from "../api/authApi.js";

export default function ResetPasswordPage() {
  const navigate      = useNavigate();
  const [params]      = useSearchParams();
  const token         = params.get("token") ?? "";

  const [password,  setPassword]  = useState("");
  const [confirm,   setConfirm]   = useState("");
  const [error,     setError]     = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [done,      setDone]      = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!token)                   return setError("Reset token is missing. Please use the link from your email.");
    if (password.length < 8)      return setError("Password must be at least 8 characters.");
    if (password !== confirm)     return setError("Passwords do not match.");

    setLoading(true);
    try {
      await resetPassword({ token, new_password: password });
      setDone(true);
    } catch (err) {
      setError(err.detail ?? "Reset failed. The link may have expired — request a new one.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "24px 16px" }}>
      <div style={{ width: "100%", maxWidth: "420px" }}>
        <div style={{ textAlign: "center", marginBottom: "32px" }}>
          <div style={{ fontSize: "40px", marginBottom: "8px" }}>🔑</div>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: "24px", color: "var(--brand-gold)" }}>
            Reset Password
          </h1>
        </div>

        <Card glow>
          {done ? (
            <div style={{ textAlign: "center", padding: "16px 0" }}>
              <div style={{ fontSize: "40px", marginBottom: "12px" }}>✅</div>
              <h3 style={{ color: "var(--color-success)", marginBottom: "8px" }}>Password updated!</h3>
              <p style={{ color: "var(--text-secondary)", marginBottom: "20px" }}>
                Your password has been reset. You can now sign in with your new password.
              </p>
              <Button fullWidth onClick={() => navigate("/", { replace: true })}>
                Go to Sign In
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate>
              <ErrorMessage message={error} />
              <Input
                label="New password"
                id="rp-password"
                type="password"
                autoComplete="new-password"
                placeholder="At least 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <Input
                label="Confirm new password"
                id="rp-confirm"
                type="password"
                autoComplete="new-password"
                placeholder="Repeat your new password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
              <Button type="submit" fullWidth loading={loading}>
                Set New Password
              </Button>
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}
