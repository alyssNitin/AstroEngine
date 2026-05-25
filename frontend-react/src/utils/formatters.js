/**
 * src/utils/formatters.js — Display formatting helpers
 * ======================================================
 * Pure functions for formatting amounts, dates, and text.
 * No side effects, no imports — safe to use anywhere.
 *
 * SOLID Notes
 * -----------
 * SRP : Each function does exactly one formatting task.
 */

// ── Currency ──────────────────────────────────────────────────────────────────

/**
 * Format an amount in minor units (cents/paise) as a currency string.
 *
 * @param {number}  cents    Amount in minor units (e.g. 1000 = $10.00)
 * @param {string}  region   ISO region code (US, IN, GB, AE …)
 * @returns {string}         e.g. "$10.00", "₹800", "£8.00"
 */
export function formatCents(cents, region = "US") {
  const CURRENCY_MAP = {
    US:  { code: "USD", locale: "en-US"    },
    IN:  { code: "INR", locale: "en-IN"    },
    GB:  { code: "GBP", locale: "en-GB"    },
    AE:  { code: "AED", locale: "ar-AE"    },
    AU:  { code: "AUD", locale: "en-AU"    },
    CA:  { code: "CAD", locale: "en-CA"    },
    SG:  { code: "SGD", locale: "en-SG"    },
    INT: { code: "USD", locale: "en-US"    },
  };

  const { code, locale } = CURRENCY_MAP[region] ?? CURRENCY_MAP.US;
  const amount = cents / 100;

  try {
    return new Intl.NumberFormat(locale, {
      style:    "currency",
      currency: code,
      minimumFractionDigits: code === "INR" ? 0 : 2,
    }).format(amount);
  } catch {
    return `${code} ${amount.toFixed(2)}`;
  }
}

/**
 * Format cents as a simple dollar string (no locale).
 * @param {number} cents
 * @returns {string}  e.g. "$12.50"
 */
export const centsToDisplay = (cents) => `$${(cents / 100).toFixed(2)}`;

// ── Dates ─────────────────────────────────────────────────────────────────────

/**
 * Format an ISO date string as a human-readable date.
 * @param {string} isoDate  e.g. "1990-03-15"
 * @returns {string}        e.g. "15 March 1990"
 */
export function formatDate(isoDate) {
  if (!isoDate) return "";
  try {
    return new Date(isoDate).toLocaleDateString("en-GB", {
      day:   "numeric",
      month: "long",
      year:  "numeric",
    });
  } catch {
    return isoDate;
  }
}

/**
 * Format an ISO datetime string as "15 Mar 2024, 14:30".
 * @param {string} iso
 * @returns {string}
 */
export function formatDateTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day:    "numeric",
      month:  "short",
      year:   "numeric",
      hour:   "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ── Text ──────────────────────────────────────────────────────────────────────

/**
 * Escape HTML special characters to prevent XSS when injecting into innerHTML.
 * @param {string} str
 * @returns {string}
 */
export function escHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Truncate a string to `maxLen` characters, appending "…" if truncated.
 * @param {string} str
 * @param {number} maxLen
 * @returns {string}
 */
export function truncate(str, maxLen = 120) {
  if (!str || str.length <= maxLen) return str ?? "";
  return str.slice(0, maxLen).trimEnd() + "…";
}

/**
 * Capitalise the first letter of a string.
 * @param {string} str
 * @returns {string}
 */
export const capitalise = (str) =>
  str ? str.charAt(0).toUpperCase() + str.slice(1) : "";
