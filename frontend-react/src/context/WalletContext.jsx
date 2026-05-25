/**
 * src/context/WalletContext.jsx — Wallet / credits state provider
 * ================================================================
 * Keeps the user's credit balance in sync across the entire app.
 * Any component that shows or deducts credits consumes this context.
 *
 * Usage:
 *   const { balanceCents, refresh, deduct } = useWallet();
 *
 * SOLID Notes
 * -----------
 * SRP : Manages only wallet/credit state.
 * DIP : Depends on walletApi abstraction.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { getWallet } from "../api/walletApi.js";
import { useAuth } from "./AuthContext.jsx";

// ── Context ───────────────────────────────────────────────────────────────────

const WalletContext = createContext(null);

// ── Provider ──────────────────────────────────────────────────────────────────

/**
 * @param {{ children: React.ReactNode }} props
 */
/** Format cents to a display string using the given region. */
function _fmt(cents, region) {
  if (region === "India") {
    const r = cents / 100;
    return `₹${r === Math.floor(r) ? Math.floor(r).toLocaleString("en-IN") : r.toFixed(2)}`;
  }
  return `$${(cents / 100).toFixed(2)}`;
}

export function WalletProvider({ children }) {
  // `user.region` from the login response is the most authoritative source.
  // We use it to format the display ourselves rather than trusting the server's
  // pre-formatted string, which can be stale if the DB region is wrong.
  const { isAuthenticated, user } = useAuth();

  const [balanceCents,   setBalanceCents]   = useState(0);
  const [region,         setRegion]         = useState("India");
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState(null);

  // Derive display from balance + region (always locally formatted)
  const balanceDisplay = _fmt(balanceCents, region);

  // ── Sync region from user object whenever login/logout ────────────────────
  useEffect(() => {
    if (user?.region) setRegion(user.region);
  }, [user?.region]);

  // ── Fetch balance ─────────────────────────────────────────────────────────
  const refresh = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getWallet();
      setBalanceCents(data.balance_cents ?? 0);
      // Only adopt server region if user object doesn't have one
      if (data.region && !user?.region) setRegion(data.region);
    } catch (err) {
      setError(err.message ?? "Failed to load wallet");
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, user?.region]);

  // Load on mount and whenever auth state changes
  useEffect(() => { refresh(); }, [refresh]);

  // ── Optimistic deduction ──────────────────────────────────────────────────
  /**
   * Subtract credits optimistically from the local balance.
   * A subsequent `refresh()` will sync the real value from the server.
   * @param {number} cents
   */
  const deduct = useCallback((cents) => {
    setBalanceCents((prev) => Math.max(0, prev - cents));
  }, []);

  // ── Helpers ───────────────────────────────────────────────────────────────

  /**
   * Format balance as a region-aware string.
   * Uses the server-provided display string when available; falls back to local formatting.
   */
  const formatBalance = useCallback(
    () => balanceDisplay,
    [balanceDisplay],
  );

  const value = {
    balanceCents,
    balanceDisplay,
    region,
    loading,
    error,
    refresh,
    deduct,
    formatBalance,
  };

  return (
    <WalletContext.Provider value={value}>{children}</WalletContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * @returns {{
 *   balanceCents: number,
 *   balanceDisplay: string,
 *   region: string,
 *   loading: boolean,
 *   error: string|null,
 *   refresh: () => Promise<void>,
 *   deduct: (cents: number) => void,
 *   formatBalance: () => string,
 * }}
 */
export function useWallet() {
  const ctx = useContext(WalletContext);
  if (!ctx) throw new Error("useWallet must be used inside <WalletProvider>");
  return ctx;
}

export default WalletContext;
