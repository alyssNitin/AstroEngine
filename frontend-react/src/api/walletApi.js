/**
 * src/api/walletApi.js — Wallet & Payment API service
 * =====================================================
 * Wraps /wallet/* and /payment/* endpoints.
 *
 * SOLID Notes
 * -----------
 * SRP : Owns only wallet/payment HTTP calls.
 * DIP : Depends on the client abstraction, not raw fetch.
 */
import { get, post } from "./client.js";

// ── Wallet ────────────────────────────────────────────────────────────────────

/**
 * Get the current user's wallet balance.
 * @returns {Promise<{ balance_cents: number, region: string }>}
 */
export const getWallet = () => get("/wallet/balance");

/**
 * Get list of available top-up packages (region-aware pricing + tax).
 * Backend: GET /payment/packs
 * @returns {Promise<{ packs: Array, region: string, currency: string }>}
 */
export const getTopupPackages = () => get("/payment/packs");

/**
 * Get the user's wallet transaction / spending history.
 * Backend: GET /payment/history
 * @param {number} page     1-based page number
 * @param {number} perPage  entries per page (max 100)
 * @returns {Promise<{ page: number, per_page: number, entries: Array, region: string }>}
 */
export const getWalletHistory = (page = 1, perPage = 20) =>
  get(`/payment/history?page=${page}&per_page=${perPage}`);

// ── Top-up ────────────────────────────────────────────────────────────────────

/**
 * Create a payment order for a wallet top-up.
 * Backend: POST /wallet/topup/order
 *
 * When no gateway keys are configured the backend returns { mock: true }
 * so the UI can skip the real payment sheet and call verifyTopup directly.
 *
 * @param {{ email: string, tier: number }} payload   tier = 1 or 2
 * @returns {Promise<{
 *   gateway: string, order_id: string, credits: number,
 *   total: number, total_display: string, mock: boolean, ...
 * }>}
 */
export const createTopupOrder = (payload) =>
  post("/wallet/topup/order", payload);

/**
 * Verify a completed payment and credit the wallet.
 * Backend: POST /wallet/topup/verify
 *
 * For mock/dev payments  → payment_data: { mock: true }
 * For Razorpay           → payment_data: { razorpay_order_id, razorpay_payment_id, razorpay_signature }
 * For Stripe             → payment_data: { payment_intent_status: "succeeded" }
 *
 * @param {{ email: string, tier: number, payment_data: object }} payload
 * @returns {Promise<{ success: boolean, new_balance_cents: number, new_balance_display: string }>}
 */
export const verifyTopup = (payload) =>
  post("/wallet/topup/verify", payload);

/**
 * Request a free demo credit (one-time per account).
 * @returns {Promise<{ message: string, credits_added: number }>}
 */
export const claimDemoCredit = () => post("/wallet/demo-credit", {});
