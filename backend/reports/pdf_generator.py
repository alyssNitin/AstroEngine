"""
backend/reports/pdf_generator.py
==================================
Generates a PDF report containing the user's deep Vedic reading and chat Q&A.
Uses only the Python standard library (html, textwrap, io) plus fpdf2 if installed;
falls back to a plain-text bytes object when fpdf2 is absent.
"""
from __future__ import annotations
import io
import re
import textwrap
from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Very lightweight HTML tag stripper."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _clean(text: str) -> str:
    return _strip_html(text).replace("’", "'").replace("‘", "'") \
                            .replace("“", '"').replace("”", '"') \
                            .replace("—", "--").replace("–", "-")


# ── Plain-text fallback ───────────────────────────────────────────────────────

def _build_plaintext(
    user_name: str,
    birth_info: str,
    refined_analysis: str,
    chat_messages: list[dict],
) -> bytes:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("  NARAYAN ASTRO READER — YOUR PERSONALISED VEDIC REPORT")
    lines.append("=" * 72)
    lines.append(f"Prepared for : {_clean(user_name)}")
    lines.append(f"Birth details: {_clean(birth_info)}")
    lines.append(f"Generated    : {datetime.utcnow().strftime('%d %B %Y, %H:%M UTC')}")
    lines.append("")
    lines.append("─" * 72)
    lines.append("PART 1 — DEEP VEDIC READING")
    lines.append("─" * 72)
    for para in _clean(refined_analysis).split("\n\n"):
        para = para.strip()
        if para:
            lines.extend(textwrap.wrap(para, 72))
            lines.append("")

    if chat_messages:
        lines.append("─" * 72)
        lines.append("PART 2 — YOUR QUESTIONS & ANSWERS")
        lines.append("─" * 72)
        for msg in chat_messages:
            role = msg.get("role", "")
            body = _clean(msg.get("content", ""))
            if role == "user" and body and body != "[Prior session restored]":
                lines.append(f"Q: {body}")
                lines.append("")
            elif role == "assistant" and body and body != "[Prior session restored]":
                for line in textwrap.wrap(body, 72):
                    lines.append(f"   {line}")
                lines.append("")

    lines.append("─" * 72)
    lines.append("© NarayanAstroReader — For personal use only.")
    return "\n".join(lines).encode("utf-8")


# ── PDF via fpdf2 ─────────────────────────────────────────────────────────────

def _build_pdf(
    user_name: str,
    birth_info: str,
    refined_analysis: str,
    chat_messages: list[dict],
) -> bytes:
    from fpdf import FPDF

    class _PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 11)
            self.set_text_color(91, 61, 200)   # brand purple
            self.cell(0, 8, "NarayanAstroReader — Personalised Vedic Report", align="C")
            self.ln(4)
            self.set_draw_color(91, 61, 200)
            self.set_line_width(0.4)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(3)

        def footer(self):
            self.set_y(-13)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 6,
                      f"Page {self.page_no()}  |  © NarayanAstroReader — For personal use only.",
                      align="C")

    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ── Meta block ────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(44, 36, 22)
    pdf.cell(0, 8, f"Reading for: {_clean(user_name)}", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 110, 95)
    pdf.cell(0, 5, f"Birth details: {_clean(birth_info)}", ln=True)
    pdf.cell(0, 5,
             f"Generated: {datetime.utcnow().strftime('%d %B %Y, %H:%M UTC')}",
             ln=True)
    pdf.ln(4)

    def _section_title(title: str) -> None:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(91, 61, 200)
        pdf.set_fill_color(245, 240, 255)
        pdf.cell(0, 8, f"  {title}", ln=True, fill=True)
        pdf.ln(2)

    def _body_text(text: str) -> None:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(44, 36, 22)
        for para in _clean(text).split("\n\n"):
            para = para.strip()
            if para:
                pdf.multi_cell(0, 5.5, para)
                pdf.ln(2)

    # ── Part 1: Deep Reading ──────────────────────────────────────────────────
    _section_title("Part 1 — Your Deep Vedic Reading")
    _body_text(refined_analysis)

    # ── Part 2: Q&A ───────────────────────────────────────────────────────────
    qa_pairs = [
        (m.get("content", ""), chat_messages[i + 1].get("content", ""))
        for i, m in enumerate(chat_messages)
        if m.get("role") == "user"
        and m.get("content", "") not in ("", "[Prior session restored]")
        and i + 1 < len(chat_messages)
        and chat_messages[i + 1].get("role") == "assistant"
    ]

    if qa_pairs:
        pdf.add_page()
        _section_title("Part 2 — Your Questions & Answers")
        for q, a in qa_pairs:
            # Question
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(91, 61, 200)
            pdf.multi_cell(0, 5.5, f"Q: {_clean(q)}")
            pdf.ln(1)
            # Answer
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(44, 36, 22)
            pdf.multi_cell(0, 5.5, _clean(a))
            pdf.ln(4)

    return bytes(pdf.output())


# ── Public API ────────────────────────────────────────────────────────────────

def generate_report_pdf(
    user_name: str,
    birth_info: str,
    refined_analysis: str,
    chat_messages: list[dict] | None = None,
) -> tuple[bytes, str]:
    """
    Returns (pdf_bytes, content_type).
    Uses fpdf2 if installed; falls back to plain UTF-8 text.
    """
    msgs = chat_messages or []
    try:
        data = _build_pdf(user_name, birth_info, refined_analysis, msgs)
        return data, "application/pdf"
    except ImportError:
        data = _build_plaintext(user_name, birth_info, refined_analysis, msgs)
        return data, "text/plain; charset=utf-8"
    except Exception:
        data = _build_plaintext(user_name, birth_info, refined_analysis, msgs)
        return data, "text/plain; charset=utf-8"
