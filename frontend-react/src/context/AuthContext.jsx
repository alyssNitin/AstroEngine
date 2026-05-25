/**
 * src/context/AuthContext.jsx — Authentication state provider
 * =============================================================
 * Provides the current user object, login/logout helpers, and a loading flag
 * to every component in the tree.
 *
 * Usage:
 *   const { user, login, logout, loading } = useAuth();
 *
 * SOLID Notes
 * -----------
 * SRP : Manages only auth state — nothing about routing or UI.
 * DIP : Depends on authApi (abstraction) not on fetch directly.
 * OCP : New auth methods (MFA, Google) can be added without changing consumers.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import * as authApi from "../api/authApi.js";
import { TOKEN_KEY } from "../api/client.js";

// ── Context Definition ────────────────────────────────────────────────────────

const AuthContext = createContext(null);

// ── Provider ──────────────────────────────────────────────────────────────────

/**
 * Wraps the application and makes auth state available everywhere.
 * @param {{ children: React.ReactNode }} props
 */
export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null);
  const [loading, setLoading] = useState(true); // true while checking token on mount

  // ── Rehydrate session on app load ────────────────────────────────────────
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    // Token exists — fetch user profile to confirm it's still valid
    authApi
      .getMe()
      .then(setUser)
      .catch(() => {
        // Token invalid or expired → clear storage
        authApi.logout();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  // ── Login ────────────────────────────────────────────────────────────────
  /**
   * Authenticate with email + password.
   * @param {string} email
   * @param {string} password
   * @returns {Promise<object>} Resolved user object
   */
  const login = useCallback(async (email, password) => {
    const data = await authApi.login({ email, password });
    setUser(data.user);
    return data.user;
  }, []);

  // ── Google Login ─────────────────────────────────────────────────────────
  /**
   * Authenticate via Google OAuth credential response.
   * @param {string} googleIdToken  JWT from Google Sign-In
   */
  const googleLogin = useCallback(async (googleIdToken) => {
    const data = await authApi.googleLogin(googleIdToken);
    setUser(data.user);
    return data.user;
  }, []);

  // ── Logout ───────────────────────────────────────────────────────────────
  const logout = useCallback(() => {
    authApi.logout();
    setUser(null);
  }, []);

  // ── Refresh user data (e.g. after wallet top-up) ─────────────────────────
  const refreshUser = useCallback(async () => {
    try {
      const fresh = await authApi.getMe();
      setUser(fresh);
      return fresh;
    } catch {
      // silently ignore — stale user data is fine for a moment
    }
  }, []);

  // ── Context value ─────────────────────────────────────────────────────────
  const value = {
    user,
    loading,
    isAuthenticated: !!user,
    login,
    logout,
    googleLogin,
    refreshUser,
    setUser, // escape hatch for profile/MFA mutations
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Consume auth state and actions.
 * Must be used inside <AuthProvider>.
 *
 * @returns {{
 *   user: object|null,
 *   loading: boolean,
 *   isAuthenticated: boolean,
 *   login: Function,
 *   logout: Function,
 *   googleLogin: Function,
 *   refreshUser: Function,
 *   setUser: Function,
 * }}
 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export default AuthContext;
