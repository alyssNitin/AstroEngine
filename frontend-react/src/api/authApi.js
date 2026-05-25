/**
 * src/api/authApi.js — Authentication API service
 * ==================================================
 * Wraps every /auth/* endpoint exposed by FastAPI.
 * All functions are pure async — they return data or throw ApiError.
 *
 * SOLID Notes
 * -----------
 * SRP : Owns only auth-related HTTP calls.
 * DIP : Depends on the client abstraction, not on raw fetch.
 */
import { get, post } from "./client.js";
import { TOKEN_KEY, REFRESH_KEY } from "./client.js";

// ── Register ──────────────────────────────────────────────────────────────────

/**
 * Register a new user account.
 * @param {{ name: string, email: string, password: string, region?: string }} payload
 * @returns {Promise<{ message: string }>}
 */
export const register = (payload) => post("/auth/register", payload);

// ── Login ─────────────────────────────────────────────────────────────────────

/**
 * Log in with email + password.
 * Stores JWT tokens in localStorage on success.
 *
 * NOTE: The backend /auth/login returns user fields flat at the top level
 * (e.g. data.email, data.name) rather than nested under a `user` key.
 * We normalise here so AuthContext.login() can always do `data.user`.
 *
 * @param {{ email: string, password: string }} credentials
 * @returns {Promise<{ access_token: string, refresh_token: string, user: object }>}
 */
export async function login(credentials) {
  const data = await post("/auth/login", credentials);
  _storeTokens(data);

  // Normalise: build a user object from the flat response fields.
  if (!data.user) {
    data.user = {
      email:                data.email,
      name:                 data.name,
      email_verified:       data.email_verified,
      user_type:            data.user_type,
      wallet_balance_cents: data.wallet_balance_cents,
      wallet_display:       data.wallet_display,
      region:               data.region,
      currency:             data.currency,
      session_id:           data.session_id,
      has_reading:          data.has_reading ?? data.has_readings ?? false,
    };
  }

  return data;
}

// ── Logout ────────────────────────────────────────────────────────────────────

/**
 * Clear local tokens and optionally notify the server.
 * (Backend may not expose a /logout route — tokens are short-lived JWTs.)
 */
export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// ── Email Verification ────────────────────────────────────────────────────────

/**
 * Verify email address using the token from the verification link.
 * @param {string} token
 * @returns {Promise<{ message: string }>}
 */
export const verifyEmail = (token) => get(`/auth/verify-email?token=${token}`);

/**
 * Re-send the verification email.
 * @param {string} email
 * @returns {Promise<{ message: string }>}
 */
export const resendVerification = (email) =>
  post("/auth/resend-verification", { email });

// ── Password Reset ────────────────────────────────────────────────────────────

/**
 * Request a password-reset link (sends email).
 * @param {string} email
 * @returns {Promise<{ message: string }>}
 */
export const forgotPassword = (email) =>
  post("/auth/forgot-password", { email });

/**
 * Complete a password reset using the token from the email link.
 * @param {{ token: string, new_password: string }} payload
 * @returns {Promise<{ message: string }>}
 */
export const resetPassword = (payload) =>
  post("/auth/reset-password", payload);

// ── Current User ──────────────────────────────────────────────────────────────

/**
 * Fetch the authenticated user's profile.
 * @returns {Promise<{ id: string, name: string, email: string, credits: number, ... }>}
 */
export const getMe = () => get("/auth/me");

// ── Google OAuth ──────────────────────────────────────────────────────────────

/**
 * Exchange a Google ID token (from Google Sign-In) for NarayanAstroReader JWTs.
 * @param {string} googleIdToken
 * @returns {Promise<{ access_token: string, refresh_token: string, user: object }>}
 */
export async function googleLogin(googleIdToken) {
  const data = await post("/auth/google", { id_token: googleIdToken });
  _storeTokens(data);
  if (!data.user) {
    data.user = {
      email:                data.email,
      name:                 data.name,
      email_verified:       data.email_verified,
      user_type:            data.user_type,
      wallet_balance_cents: data.wallet_balance_cents,
      wallet_display:       data.wallet_display,
      region:               data.region,
      currency:             data.currency,
      session_id:           data.session_id,
      has_reading:          data.has_reading ?? data.has_readings ?? false,
    };
  }
  return data;
}

// ── MFA ───────────────────────────────────────────────────────────────────────

/** Begin MFA setup — returns { qr_code_url, secret } */
export const setupMfa    = ()          => post("/auth/mfa/setup",   {});

/** Confirm MFA setup with a TOTP code */
export const confirmMfa  = (code)      => post("/auth/mfa/confirm", { code });

/** Disable MFA */
export const disableMfa  = (code)      => post("/auth/mfa/disable", { code });

// ── Profiles (multi-chart) ────────────────────────────────────────────────────

/** List all saved kundli profiles for the current user */
export const listProfiles = ()            => get("/auth/profiles");

/** Create a new profile */
export const createProfile = (payload)    => post("/auth/profiles", payload);

/** Activate a profile (switches active birth data) */
export const activateProfile = (id)       => post(`/auth/profiles/${id}/activate`, {});

/** Delete a profile */
export const deleteProfile   = (id)       => post(`/auth/profiles/${id}/delete`, {});

// ── Helper ────────────────────────────────────────────────────────────────────

/** Persist tokens returned by login / google-login / refresh */
function _storeTokens(data) {
  if (data.access_token)  localStorage.setItem(TOKEN_KEY,   data.access_token);
  if (data.refresh_token) localStorage.setItem(REFRESH_KEY, data.refresh_token);
}
