"""
payment/wallet.py
==================
Region-aware wallet service.
All amounts stored as integer "minor units":
  India        : paise  (1 ₹ = 100 paise)
  International: cents  (1 $ = 100 cents)

India rules
-----------
  Welcome credit   : ₹100  (10 000 paise)
  Kundli + Reading : ₹100  (10 000 paise)
  Chat message     : ₹25   ( 2 500 paise)
  Recharge ₹99     → ₹110 credited  (~10 % bonus)
  Recharge ₹249    → ₹300 credited  (₹51 gift, as specified)

International (USD) rules
--------------------------
  Welcome credit   : $1.00 (100 cents)
  Kundli + Reading : $1.00 (100 cents)
  Chat message     : $1.00 (100 cents)
  Recharge $10     → $11 credited ($1 gift, 10 % bonus)
  Recharge $25     → $30 credited ($5 gift, 20 % bonus)
  Minimum recharge : $10
"""
from __future__ import annotations
import os

GUEST_FREE_CHAT_LIMIT = int(os.environ.get("GUEST_FREE_CHAT_LIMIT", "3"))

# ── India pricing (paise; 1 ₹ = 100 paise) ───────────────────────────────────
INDIA_WELCOME_CREDIT    = 10_000   # ₹100
INDIA_REPORT_COST       = 10_000   # ₹100 per kundli + deep reading
INDIA_CHAT_COST         =  2_500   # ₹25  per chat question

INDIA_TIER1_PRICE_PAISE =  9_900   # ₹99  paid by user
INDIA_TIER1_CREDIT      = 11_000   # ₹110 credited (~10 % bonus)
INDIA_TIER2_PRICE_PAISE = 24_900   # ₹249 paid by user
INDIA_TIER2_CREDIT      = 30_000   # ₹300 credited (₹51 gift, per spec)

# ── International pricing (USD cents; 1 $ = 100 cents) ────────────────────────
INTL_WELCOME_CREDIT     =   100   # $1.00
INTL_REPORT_COST        =   100   # $1.00 per kundli + deep reading
INTL_CHAT_COST          =   100   # $1.00 per chat question (per spec)

INTL_TIER1_PRICE_CENTS  = 1_000   # $10 paid by user
INTL_TIER1_CREDIT       = 1_100   # $11 credited ($1 gift)
INTL_TIER2_PRICE_CENTS  = 2_500   # $25 paid by user
INTL_TIER2_CREDIT       = 3_000   # $30 credited ($5 gift)

REGIONS = {"India", "International"}

# ── Tax rates ─────────────────────────────────────────────────────────────────
# India: 18% GST on digital services (SAC code 998439)
# International: 0% — collected by local jurisdiction where applicable
INDIA_GST_RATE  = 0.18   # 18% GST
INTL_TAX_RATE   = 0.00   # 0% (no tax collected — user's jurisdiction applies)


def calculate_tax(subtotal_minor: int, region: str) -> dict:
    """
    Calculate tax for a payment amount.

    Parameters
    ----------
    subtotal_minor : Amount in minor units (paise for India, cents for International)
                     This is the BASE amount BEFORE tax (exclusive tax model).
    region         : "India" or "International"

    Returns
    -------
    dict with keys:
        subtotal       : base amount (minor units, pre-tax)
        tax_amount     : tax in minor units
        total          : subtotal + tax (what customer pays)
        tax_rate       : decimal rate applied (e.g. 0.18)
        tax_label      : human-readable label ("18% GST", "No tax", etc.)
        tax_display    : formatted tax string (e.g. "₹17.82")
        total_display  : formatted total string (e.g. "₹116.82")
        subtotal_display: formatted subtotal string
    """
    rate = INDIA_GST_RATE if region == "India" else INTL_TAX_RATE
    tax_minor = round(subtotal_minor * rate)
    total_minor = subtotal_minor + tax_minor

    symbol = "₹" if region == "India" else "$"
    divisor = 100   # both paise and cents use 100 minor units per major unit

    def _fmt(minor: int) -> str:
        return f"{symbol}{minor / divisor:.2f}"

    if region == "India":
        tax_label = f"GST @ {int(rate * 100)}%"
    elif rate == 0:
        tax_label = "No tax"
    else:
        tax_label = f"Tax @ {int(rate * 100)}%"

    return {
        "subtotal":         subtotal_minor,
        "tax_amount":       tax_minor,
        "total":            total_minor,
        "tax_rate":         rate,
        "tax_label":        tax_label,
        "tax_display":      _fmt(tax_minor),
        "total_display":    _fmt(total_minor),
        "subtotal_display": _fmt(subtotal_minor),
    }


def get_pricing(region: str) -> dict:
    """Return cost constants and display info for the given region."""
    if region == "India":
        return {
            "welcome":      INDIA_WELCOME_CREDIT,
            "report":       INDIA_REPORT_COST,
            "chat":         INDIA_CHAT_COST,
            "tier1_price":  INDIA_TIER1_PRICE_PAISE,
            "tier1_credit": INDIA_TIER1_CREDIT,
            "tier1_label":  "₹99",
            "tier1_value":  "₹110",
            "tier1_gift":   "₹11 gift",
            "tier2_price":  INDIA_TIER2_PRICE_PAISE,
            "tier2_credit": INDIA_TIER2_CREDIT,
            "tier2_label":  "₹249",
            "tier2_value":  "₹300",
            "tier2_gift":   "₹51 gift",
            "currency":     "INR",
            "symbol":       "₹",
            "min_topup":    "₹99",
        }
    return {
        "welcome":      INTL_WELCOME_CREDIT,
        "report":       INTL_REPORT_COST,
        "chat":         INTL_CHAT_COST,
        "tier1_price":  INTL_TIER1_PRICE_CENTS,
        "tier1_credit": INTL_TIER1_CREDIT,
        "tier1_label":  "$10",
        "tier1_value":  "$11",
        "tier1_gift":   "$1 gift",
        "tier2_price":  INTL_TIER2_PRICE_CENTS,
        "tier2_credit": INTL_TIER2_CREDIT,
        "tier2_label":  "$25",
        "tier2_value":  "$30",
        "tier2_gift":   "$5 gift",
        "currency":     "USD",
        "symbol":       "$",
        "min_topup":    "$10",
    }


def format_amount(minor_units: int, region: str) -> str:
    """Format minor units as human-readable amount with currency symbol."""
    if region == "India":
        rupees = minor_units / 100
        if rupees == int(rupees):
            return f"₹{int(rupees):,}"
        return f"₹{rupees:,.2f}"
    dollars = minor_units / 100
    return f"${dollars:.2f}"


def label_txn_reason(reason: str, region: str) -> str:
    """Convert raw reason codes to user-friendly labels."""
    labels = {
        "kundli_report":        "Kundli + Deep Reading",
        "chat_message":         "AI Astrologer Question",
        "welcome_verification": "Welcome Credit (Email Verified)",
        "topup":                "Wallet Recharge",
        "refund_ai_error":      "Refund (AI Error)",
        "admin":                "Admin Adjustment",
    }
    for key, label in labels.items():
        if key in reason:
            return label
    if "gift" in reason or "bonus" in reason:
        return "Bonus Gift Credit"
    return reason.replace("_", " ").title()


# ── Legacy constants (kept so existing imports don't break) ───────────────────
WELCOME_CREDIT_CENTS  = INTL_WELCOME_CREDIT
REPORT_COST_CENTS     = INTL_REPORT_COST
CHAT_COST_CENTS       = INTL_CHAT_COST
TOPUP_1_CENTS         = INTL_TIER1_CREDIT
TOPUP_1_PRICE_INR     = INDIA_TIER1_PRICE_PAISE
TOPUP_2_CENTS         = INTL_TIER2_CREDIT
TOPUP_2_PRICE_INR     = INDIA_TIER2_PRICE_PAISE
FREE_CREDITS_ON_REGISTER = 0
CREDITS_PER_READING      = REPORT_COST_CENTS
CREDITS_PER_TOPUP        = TOPUP_1_CENTS
TOPUP_PRICE_INR          = TOPUP_1_PRICE_INR


class WalletService:
    """Region-aware wallet facade over Database methods."""

    @staticmethod
    def get_balance(db, email: str) -> int:
        return db.get_wallet_balance_cents(email)

    @staticmethod
    def get_region(db, email: str) -> str:
        profile = db.get_profile(email) or {}
        return profile.get("region", "India")

    @staticmethod
    def get_pricing_for_user(db, email: str) -> dict:
        return get_pricing(WalletService.get_region(db, email))

    @staticmethod
    def debit(db, email: str, amount: int, reason: str = "") -> tuple:
        return db.debit_wallet_cents(email, amount, reason)

    @staticmethod
    def credit(db, email: str, amount: int, reason: str = "") -> int:
        return db.credit_wallet_cents(email, amount, reason)

    @staticmethod
    def refund(db, email: str, amount: int) -> int:
        return db.credit_wallet_cents(email, amount, reason="refund_ai_error")

    @staticmethod
    def topup(db, email: str, credits: int, bonus: int = 0,
              reference_id: str = "") -> int:
        # Real-money portion -> paid_balance; gift/bonus -> promo_balance
        if credits:
            db.credit_wallet_cents(email, credits, reason="topup",
                                   is_paid=True, reference_id=reference_id)
        if bonus:
            db.credit_wallet_cents(email, bonus, reason=f"gift_{bonus}",
                                   is_paid=False, reference_id=reference_id)
        return db.get_wallet_balance_cents(email)

    @staticmethod
    def grant_welcome_credit(db, email: str) -> int:
        region = WalletService.get_region(db, email)
        amount = get_pricing(region)["welcome"]
        return db.credit_wallet_cents(email, amount, reason="welcome_verification")

    @staticmethod
    def can_afford_report(db, email: str) -> bool:
        return db.get_wallet_balance_cents(email) >= WalletService.get_pricing_for_user(db, email)["report"]

    @staticmethod
    def can_afford_chat(db, email: str) -> bool:
        return db.get_wallet_balance_cents(email) >= WalletService.get_pricing_for_user(db, email)["chat"]

    @staticmethod
    def format_balance(minor_units: int, region: str) -> str:
        return format_amount(minor_units, region)

    @staticmethod
    def format_dollars(cents: int) -> str:
        """Legacy compat."""
        return f"${cents / 100:.2f}"
