/**
 * src/components/wallet/WalletModal.jsx — Wallet modal: balance + history + top-up
 * ==================================================================================
 * Bug fixes applied in this version:
 *   BUG-1: handleTopup was a placeholder. Now calls POST /wallet/topup/order then
 *           POST /wallet/topup/verify — mock-safe (works without real gateway keys).
 *   BUG-2: isDebit used (amount_cents < 0) but ledger stores all amounts as positive.
 *           Fixed to read txn_type/type field for direction.
 *
 * SOLID Notes
 * -----------
 * SRP : Manages only wallet display and top-up.
 * DIP : Uses walletApi + useAuth abstractions.
 */
import React, { useCallback, useEffect, useState } from "react";
import Modal        from "../ui/Modal.jsx";
import Button       from "../ui/Button.jsx";
import Spinner      from "../ui/Spinner.jsx";
import ErrorMessage from "../ui/ErrorMessage.jsx";
import { useAuth }   from "../../context/AuthContext.jsx";
import { useWallet } from "../../context/WalletContext.jsx";
import {
  getTopupPackages, getWalletHistory,
  createTopupOrder, verifyTopup,
} from "../../api/walletApi.js";

// ── Region normaliser ─────────────────────────────────────────────────────────
const REGION_TO_CODE = {
  India: "IN", US: "US", "United States": "US",
  GB: "GB", UK: "GB", AE: "AE", AU: "AU", CA: "CA", SG: "SG",
};
const regionCode = (r) => REGION_TO_CODE[r] ?? "IN";

// ── Currency formatter ────────────────────────────────────────────────────────
const CURRENCY = {
  IN: { symbol: "₹", locale: "en-IN",  code: "INR" },
  US: { symbol: "$", locale: "en-US",  code: "USD" },
  GB: { symbol: "£", locale: "en-GB",  code: "GBP" },
  AE: { symbol: "AED",locale: "ar-AE", code: "AED" },
  AU: { symbol: "A$",locale: "en-AU",  code: "AUD" },
  CA: { symbol: "CA$",locale: "en-CA", code: "CAD" },
  SG: { symbol: "S$",locale: "en-SG",  code: "SGD" },
};
function fmtCents(cents, region) {
  const code = regionCode(region);
  const cur  = CURRENCY[code] ?? CURRENCY.IN;
  const amount = Math.abs(cents) / 100;
  try {
    return new Intl.NumberFormat(cur.locale, {
      style: "currency", currency: cur.code,
      minimumFractionDigits: code === "IN" ? 0 : 2,
    }).format(amount);
  } catch {
    return `${cur.symbol}${amount.toFixed(2)}`;
  }
}

// ── Date formatter ────────────────────────────────────────────────────────────
function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return String(iso); }
}

// ── Transaction helpers ───────────────────────────────────────────────────────
/**
 * FIX (Bug 2): Ledger rows use txn_type; legacy JSON uses type.
 * Amount is ALWAYS stored as a positive integer — direction = txn_type/type.
 */
function isDebitTxn(tx) {
  return (tx.txn_type ?? tx.type ?? "") === "debit";
}

function txMeta(tx) {
  const type   = tx.txn_type ?? tx.type ?? "";
  const reason = tx.reason   ?? "";
  if (type === "debit") {
    if (reason.includes("chat"))   return { label: "Chat Question", color: "#a78bfa" };
    if (reason.includes("kundli")) return { label: "Reading",       color: "#ef4444" };
    return                                { label: "Debit",         color: "#ef4444" };
  }
  if (reason.includes("topup")   || type === "topup")        return { label: "Top Up",        color: "#22c55e" };
  if (reason.includes("refund")  || type === "refund")       return { label: "Refund",        color: "#22c55e" };
  if (reason.includes("promo")   && !reason.includes("exp")) return { label: "Promo Credit",  color: "#f59e0b" };
  if (reason.includes("expiry")  || type === "promo_expiry") return { label: "Promo Expired", color: "#ef4444" };
  if (reason.includes("welcome"))                            return { label: "Welcome Bonus", color: "#f59e0b" };
  if (reason.includes("demo"))                               return { label: "Demo Credit",   color: "#f59e0b" };
  if (type === "credit")                                     return { label: "Credit",        color: "#22c55e" };
  return { label: type || "Transaction", color: "var(--text-secondary)" };
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
const TABS = { HISTORY: "history", TOPUP: "topup" };

// ── Component ─────────────────────────────────────────────────────────────────
export default function WalletModal({ isOpen, onClose, region = "India" }) {
  const { user }                  = useAuth();
  const { balanceCents, refresh } = useWallet();

  const [tab,       setTab]       = useState(TABS.HISTORY);
  const [history,   setHistory]   = useState([]);
  const [packages,  setPackages]  = useState([]);
  const [histLoad,  setHistLoad]  = useState(false);
  const [pkgLoad,   setPkgLoad]   = useState(false);
  const [histErr,   setHistErr]   = useState(null);
  const [pkgErr,    setPkgErr]    = useState(null);
  const [topupMsg,  setTopupMsg]  = useState(null);  // {text, type}
  const [topupLoad, setTopupLoad] = useState(false);

  // ── Load history + packages when modal opens ──────────────────────────────
  const loadData = useCallback(() => {
    if (!isOpen) return;

    setHistLoad(true); setHistErr(null);
    getWalletHistory(1, 30)
      .then((d) => setHistory(d.entries ?? []))
      .catch(() => setHistErr("Could not load transaction history."))
      .finally(() => setHistLoad(false));

    setPkgLoad(true); setPkgErr(null);
    getTopupPackages()
      .then((d) => setPackages(d.packs ?? []))
      .catch(() => setPkgErr("Could not load top-up options."))
      .finally(() => setPkgLoad(false));
  }, [isOpen]);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => { if (!isOpen) { setTab(TABS.HISTORY); setTopupMsg(null); } }, [isOpen]);

  // ── Top-up handler (BUG-1 FIX) ───────────────────────────────────────────
  async function handleTopup(pkg) {
    if (!user?.email) {
      setTopupMsg({ text: "Please log in to top up your wallet.", type: "error" });
      return;
    }
    setTopupLoad(true);
    setTopupMsg(null);

    try {
      // Step 1 – create the order (backend returns mock:true when no gateway keys)
      const order = await createTopupOrder({ email: user.email, tier: pkg.tier });

      if (order.mock) {
        // Dev / demo mode: no real payment keys set.
        // Call verify directly with mock:true → wallet is credited immediately.
        const result = await verifyTopup({
          email:        user.email,
          tier:         pkg.tier,
          payment_data: { mock: true },
        });

        if (result.success) {
          await refresh();   // refresh WalletContext (header balance chip)
          await loadData();  // reload history so new credit appears immediately
          setTopupMsg({
            text: `✅ Wallet topped up! New balance: ${result.new_balance_display}`,
            type: "success",
          });
        } else {
          setTopupMsg({ text: "Top-up did not complete. Please try again.", type: "error" });
        }
      } else {
        // Production: open Razorpay / Stripe checkout here.
        // TODO: integrate checkout.js / stripe.js
        setTopupMsg({
          text: `Order ${order.order_id} created (${order.total_display}). Connect your payment gateway to complete checkout.`,
          type: "info",
        });
      }
    } catch (err) {
      setTopupMsg({
        text: err?.detail ?? err?.message ?? "Top-up failed. Please try again.",
        type: "error",
      });
    } finally {
      setTopupLoad(false);
    }
  }

  // ── Tab styles ────────────────────────────────────────────────────────────
  const tabStyle = (active) => ({
    flex: 1, padding: "10px 0", background: "none", border: "none",
    borderBottom: active ? "2px solid var(--brand-purple)" : "2px solid transparent",
    color: active ? "var(--text-primary)" : "var(--text-muted)",
    fontWeight: active ? "600" : "400", fontSize: "14px",
    cursor: "pointer", transition: "all 0.15s", marginBottom: "-1px",
  });

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="💰 My Wallet" maxWidth={460}>

      {/* ── Balance card ───────────────────────────────────────────────── */}
      <div style={{
        textAlign: "center", padding: "20px 16px",
        background: "linear-gradient(135deg,rgba(107,70,193,.15),rgba(212,175,55,.08))",
        borderRadius: "var(--radius-md)", border: "1px solid var(--surface-border)",
        marginBottom: "20px",
      }}>
        <p style={{ color: "var(--text-secondary)", fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>
          Current Balance
        </p>
        <p style={{ fontFamily: "var(--font-heading)", fontSize: "36px", color: "var(--brand-gold)", lineHeight: 1 }}>
          {fmtCents(balanceCents, region)}
        </p>
        <p style={{ color: "var(--text-muted)", fontSize: "11px", marginTop: "6px" }}>
          Credits for AI readings &amp; reports
        </p>
      </div>

      {/* ── Tab bar ────────────────────────────────────────────────────── */}
      <div role="tablist" style={{ display: "flex", borderBottom: "1px solid var(--surface-border)", marginBottom: "16px" }}>
        <button role="tab" aria-selected={tab === TABS.HISTORY} onClick={() => setTab(TABS.HISTORY)} style={tabStyle(tab === TABS.HISTORY)}>
          📋 History
        </button>
        <button role="tab" aria-selected={tab === TABS.TOPUP} onClick={() => setTab(TABS.TOPUP)} style={tabStyle(tab === TABS.TOPUP)}>
          ➕ Top Up
        </button>
      </div>

      {/* ── HISTORY TAB ────────────────────────────────────────────────── */}
      {tab === TABS.HISTORY && (
        <div>
          {histErr && <ErrorMessage message={histErr} type="error" />}

          {histLoad ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "32px" }}>
              <Spinner size={32} />
            </div>
          ) : history.length === 0 ? (
            <div style={{ textAlign: "center", padding: "32px 16px" }}>
              <div style={{ fontSize: "32px", marginBottom: "8px" }}>📭</div>
              <p style={{ color: "var(--text-muted)", fontSize: "14px" }}>No transactions yet.</p>
            </div>
          ) : (
            <div style={{ maxHeight: "300px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "6px" }}>
              {history.map((tx, i) => {
                const debit   = isDebitTxn(tx);
                const { label, color } = txMeta(tx);
                const amount  = Math.abs(tx.amount_cents ?? tx.amount ?? 0);
                const display = tx.amount_display ?? fmtCents(amount, region);
                const dateStr = fmtDate(tx.created_at ?? tx.ts);

                return (
                  <div key={tx.id ?? i} style={{
                    display: "flex", alignItems: "center", gap: "12px",
                    padding: "10px 12px",
                    background: "var(--surface-elevated)",
                    borderRadius: "var(--radius-base)",
                    border: "1px solid var(--surface-border)",
                  }}>
                    {/* Icon bubble */}
                    <div style={{
                      width: "32px", height: "32px", borderRadius: "50%",
                      background: `${color}22`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: "14px", flexShrink: 0,
                    }}>
                      {debit ? "⬇" : "⬆"}
                    </div>

                    {/* Label + date */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "2px" }}>
                        {label}
                      </p>
                      {tx.description && (
                        <p style={{ fontSize: "11px", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {tx.description}
                        </p>
                      )}
                      {dateStr && (
                        <p style={{ fontSize: "11px", color: "var(--text-muted)" }}>{dateStr}</p>
                      )}
                    </div>

                    {/* Amount — sign correct via txn_type */}
                    <div style={{ fontSize: "14px", fontWeight: "700", color, flexShrink: 0 }}>
                      {debit ? "−" : "+"}{display}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <p style={{ color: "var(--text-muted)", fontSize: "11px", textAlign: "center", marginTop: "12px" }}>
            Showing last 30 transactions
          </p>
        </div>
      )}

      {/* ── TOP UP TAB ─────────────────────────────────────────────────── */}
      {tab === TABS.TOPUP && (
        <div>
          {topupMsg && (
            <ErrorMessage message={topupMsg.text} type={topupMsg.type ?? "success"} />
          )}
          {pkgErr && <ErrorMessage message={pkgErr} type="error" />}

          {pkgLoad ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "32px" }}>
              <Spinner size={32} />
            </div>
          ) : packages.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "14px", textAlign: "center", padding: "24px" }}>
              No top-up packages available right now.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {packages.map((pkg) => (
                <button
                  key={pkg.tier}
                  onClick={() => handleTopup(pkg)}
                  disabled={topupLoad}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "16px",
                    background: "var(--surface-elevated)",
                    border: "1.5px solid var(--surface-border)",
                    borderRadius: "var(--radius-md)",
                    cursor: topupLoad ? "not-allowed" : "pointer",
                    opacity: topupLoad ? 0.7 : 1,
                    transition: "border-color 0.15s, background 0.15s",
                    color: "var(--text-primary)", textAlign: "left", width: "100%",
                  }}
                  onMouseEnter={(e) => {
                    if (!topupLoad) {
                      e.currentTarget.style.borderColor = "var(--brand-purple)";
                      e.currentTarget.style.background  = "rgba(107,70,193,0.08)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--surface-border)";
                    e.currentTarget.style.background  = "var(--surface-elevated)";
                  }}
                >
                  <div>
                    <p style={{ fontWeight: "700", fontSize: "15px", marginBottom: "2px" }}>
                      {pkg.label}
                      {pkg.tier === 2 && (
                        <span style={{ marginLeft: "8px", fontSize: "11px", background: "var(--brand-purple)", color: "#fff", padding: "2px 6px", borderRadius: "9999px" }}>
                          POPULAR
                        </span>
                      )}
                    </p>
                    <p style={{ color: "var(--text-secondary)", fontSize: "12px" }}>
                      {pkg.credit_display ?? `${pkg.credits} credits`}
                      {pkg.tax_label && ` · ${pkg.tax_label}`}
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
                    {topupLoad && <Spinner size={16} />}
                    <div style={{ textAlign: "right" }}>
                      <p style={{ color: "var(--brand-gold)", fontWeight: "700", fontSize: "18px" }}>
                        {pkg.total_display}
                      </p>
                      {pkg.subtotal_display && pkg.subtotal_display !== pkg.total_display && (
                        <p style={{ color: "var(--text-muted)", fontSize: "11px" }}>+tax</p>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}

          <p style={{ color: "var(--text-muted)", fontSize: "11px", marginTop: "16px", textAlign: "center" }}>
            🔒 Credits do not expire (promotional credits expire in 30 days).
          </p>
        </div>
      )}
    </Modal>
  );
}
