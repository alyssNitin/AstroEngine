/**
 * src/api/client.js — Base HTTP client
 * ======================================
 * Centralised fetch wrapper that:
 *   - Attaches the JWT access token from localStorage automatically
 *   - Intercepts 401 responses and attempts a silent token refresh
 *   - Exposes a typed ApiError so callers can distinguish HTTP errors
 *
 * SOLID Notes
 * -----------
 * SRP : This module owns exactly one concern — making authenticated HTTP
 *       requests.  It knows nothing about auth logic, UI, or domain models.
 * DIP : Higher-level modules (authApi, kundliApi …) depend on this
 *       abstraction, not on raw fetch.
 * OCP : Adding request/response interceptors is easy — just extend the
 *       `_interceptors` arrays below without touching existing callers.
 */

// ── Token Storage Keys ────────────────────────────────────────────────────────
export const TOKEN_KEY   = "nar_access_token";
export const REFRESH_KEY = "nar_refresh_token";

// ── API base URL ──────────────────────────────────────────────────────────────
// In dev, Vite proxies /auth, /kundli etc. to localhost:8000.
// In production the React build is served from the same origin as FastAPI.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// ── Custom error class ────────────────────────────────────────────────────────

/**
 * Represents an HTTP error returned by the API.
 * Callers can inspect `.status` and `.detail` to show appropriate messages.
 */
export class ApiError extends Error {
  /**
   * @param {number} status   HTTP status code
   * @param {string} detail   Human-readable error message from the server
   * @param {*}      [body]   Raw response body (if available)
   */
  constructor(status, detail, body = null) {
    super(detail);
    this.name   = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body   = body;
  }
}

// ── Refresh lock — prevents parallel refresh calls ────────────────────────────
let _refreshPromise = null;

/**
 * Silently exchange the refresh token for a new access token.
 * @returns {Promise<string>} New access token, or throws if refresh fails.
 */
async function _refreshAccessToken() {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) throw new ApiError(401, "No refresh token available");

  const res = await fetch(`${BASE_URL}/auth/refresh`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!res.ok) {
    // Refresh failed — clear everything so app redirects to login
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    throw new ApiError(401, "Session expired. Please log in again.");
  }

  const data = await res.json();
  localStorage.setItem(TOKEN_KEY, data.access_token);
  if (data.refresh_token) localStorage.setItem(REFRESH_KEY, data.refresh_token);
  return data.access_token;
}

// ── Core request function ─────────────────────────────────────────────────────

/**
 * Make an authenticated HTTP request.
 *
 * @param {string}  path             URL path (e.g. "/auth/login")
 * @param {object}  [options]        Standard fetch options
 * @param {boolean} [retry=true]     Whether to retry once after token refresh
 * @returns {Promise<*>}             Parsed JSON body
 * @throws  {ApiError}               On non-2xx responses
 */
async function request(path, options = {}, retry = true) {
  const accessToken = localStorage.getItem(TOKEN_KEY);

  const headers = {
    "Content-Type": "application/json",
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...options.headers,
  };

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  // ── 401: attempt silent token refresh once ────────────────────────────────
  if (response.status === 401 && retry) {
    if (!_refreshPromise) {
      _refreshPromise = _refreshAccessToken().finally(() => {
        _refreshPromise = null;
      });
    }
    try {
      await _refreshPromise;
      return request(path, options, false); // retry with new token
    } catch {
      throw new ApiError(401, "Session expired. Please log in again.");
    }
  }

  // ── Parse body ────────────────────────────────────────────────────────────
  let body;
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    body = await response.json();
  } else if (contentType.includes("text/")) {
    body = await response.text();
  } else {
    body = await response.blob();
  }

  if (!response.ok) {
    const detail =
      (typeof body === "object" && body?.detail) ||
      (typeof body === "string" && body) ||
      `HTTP ${response.status}`;
    throw new ApiError(response.status, detail, body);
  }

  return body;
}

// ── Public helpers ────────────────────────────────────────────────────────────

/** GET  /path */
export const get  = (path, opts)         => request(path, { ...opts, method: "GET" });

/** POST /path with JSON body */
export const post = (path, data, opts)   => request(path, { ...opts, method: "POST",  body: JSON.stringify(data) });

/** PUT  /path with JSON body */
export const put  = (path, data, opts)   => request(path, { ...opts, method: "PUT",   body: JSON.stringify(data) });

/** DELETE /path */
export const del  = (path, opts)         => request(path, { ...opts, method: "DELETE" });

/** PATCH /path with JSON body */
export const patch = (path, data, opts)  => request(path, { ...opts, method: "PATCH", body: JSON.stringify(data) });

/**
 * POST with FormData (for file uploads etc.)
 * Does NOT set Content-Type — browser sets it with boundary automatically.
 */
export const postForm = (path, formData, opts) =>
  request(path, {
    ...opts,
    method:  "POST",
    body:    formData,
    headers: { ...(opts?.headers ?? {}) }, // no Content-Type override
  });

export default { get, post, put, del, patch, postForm, ApiError };
