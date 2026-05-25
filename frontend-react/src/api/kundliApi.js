/**
 * src/api/kundliApi.js — Kundli / Reading API service
 * =====================================================
 * Wraps every /kundli/* endpoint: starting a reading, refining predictions,
 * emailing / downloading reports, and compatibility/career features.
 *
 * SOLID Notes
 * -----------
 * SRP : Owns only kundli-related HTTP calls.
 * DIP : Depends on the client abstraction, not raw fetch.
 */
import { get, post, TOKEN_KEY } from "./client.js";

// ── Start Reading ─────────────────────────────────────────────────────────────

/**
 * Start a new Vedic reading session.
 *
 * @param {{
 *   name: string,
 *   date_of_birth: string,   // "YYYY-MM-DD"
 *   time_of_birth: string,   // "HH:MM"
 *   place_of_birth: string,
 *   gender: string,
 *   language?: string,
 *   report_type?: string,
 *   email?: string,
 * }} payload
 *
 * @returns {Promise<{
 *   session_id: string,
 *   predictions: Array<{id: string, statement: string, category: string, emoji: string, question: string}>,
 *   overall_theme: string,
 *   lagna: object,
 *   birth_info: object,
 *   wallet_balance_cents: number,
 *   wallet_display: string,
 * }>}
 */
export const startReading = (payload) => post("/kundli/start", payload);

// ── Refine Reading (SSE streaming) ───────────────────────────────────────────

/**
 * Submit confirmed/corrected predictions and consume the SSE deep-reading stream.
 *
 * Backend endpoint : POST /kundli/refine/{session_id}   (session_id is a PATH param)
 * Backend payload  : { corrections: { [domainId]: "confirmed" | "correction text" },
 *                      email: string, language: string }
 * Backend SSE events:
 *   data: {"chunk": "..."}        — incremental text
 *   data: {"done": true, ...}     — stream complete, includes wallet metadata
 *   data: {"error": "...", ...}   — stream failed
 *
 * @param {{
 *   session_id:    string,
 *   confirmations: Array<{id: string, confirmed: boolean|null, correction: string}>,
 *   email?:        string,
 *   language?:     string,
 *   onChunk?:      (chunkText: string) => void,  // optional live-stream callback
 * }} params
 *
 * @returns {Promise<{ refined_reading: string, wallet_balance_cents?: number, wallet_display?: string }>}
 */
export async function refineReading({
  session_id,
  confirmations,
  email    = "",
  language = "English",
  onChunk  = null,
}) {
  // ── Transform confirmations array → corrections dict ──────────────────────
  // Prediction IDs are domain names: "career", "marriage", "education", etc.
  // Backend planet_calibrator uses corrections[domain] as free-text feedback.
  // Confirmed    → "confirmed" (or user's note if they added one)
  // Corrected    → the correction text
  // Unreviewed   → skip (UI validates before submit)
  const corrections = {};
  for (const p of confirmations) {
    if (p.confirmed === null) continue;
    corrections[p.id] = p.confirmed
      ? (p.correction?.trim() || "confirmed")
      : (p.correction?.trim() || "not accurate");
  }

  // ── Fetch with raw SSE stream — cannot use post() helper (it parses JSON) ──
  const token = localStorage.getItem(TOKEN_KEY);
  const res   = await fetch(`/kundli/refine/${session_id}`, {
    method:  "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ corrections, email, language }),
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw { detail };
  }

  // ── Read SSE stream until { done: true } fires ────────────────────────────
  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let fullText  = "";
  let doneData  = null;
  let buffer    = "";

  outer: while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    // SSE events are delimited by double newlines
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";   // keep the incomplete trailing fragment

    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        let evt;
        try { evt = JSON.parse(line.slice(6)); } catch { continue; }

        if (evt.chunk !== undefined) {
          fullText += evt.chunk;
          onChunk?.(evt.chunk);
        } else if (evt.done) {
          doneData = evt;
          break outer;
        } else if (evt.error) {
          const err = { detail: evt.error, refunded: evt.refunded ?? false };
          throw err;
        }
      }
    }
  }

  return {
    refined_reading: fullText,
    ...(doneData ?? {}),
  };
}

// ── Q&A (Chat) ────────────────────────────────────────────────────────────────

/**
 * Ask a follow-up question within an active session.
 *
 * @param {{ session_id: string, question: string }} payload
 * @returns {Promise<{ answer: string, credits_remaining: number }>}
 */
export const askQuestion = (payload) => post("/kundli/question", payload);

// ── Reports ───────────────────────────────────────────────────────────────────

/**
 * Request the server to email the PDF/text report to the user.
 * @param {{ session_id: string }} payload
 * @returns {Promise<{ message: string }>}
 */
export const emailReport = (payload) => post("/kundli/email-report", payload);

/**
 * Download the reading report as a Blob.
 * @param {string} sessionId
 * @param {"pdf"|"txt"} format
 * @returns {Promise<Blob>}
 */
export async function downloadReport(sessionId, format = "pdf") {
  const res = await fetch(`/kundli/download-report?session_id=${sessionId}&format=${format}`, {
    headers: {
      Authorization: `Bearer ${localStorage.getItem("nar_access_token")}`,
    },
  });
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  return res.blob();
}

// ── Career Report ─────────────────────────────────────────────────────────────

/**
 * Generate a career-specific Vedic report.
 * @param {{ session_id: string }} payload
 * @returns {Promise<{ career_report: string }>}
 */
export const generateCareerReport = (payload) =>
  post("/kundli/career-report", payload);

// ── Compatibility ─────────────────────────────────────────────────────────────

/**
 * Generate a Vedic compatibility (synastry) report between two people.
 *
 * @param {{
 *   session_id: string,
 *   partner_name: string,
 *   partner_dob: string,
 *   partner_tob: string,
 *   partner_city: string,
 *   partner_country: string,
 *   partner_gender: string,
 * }} payload
 * @returns {Promise<{ compat_report: string }>}
 */
export const generateCompatReport = (payload) =>
  post("/kundli/compat-report", payload);

// ── Share ─────────────────────────────────────────────────────────────────────

/**
 * Create a shareable link for a reading session.
 * @param {{ session_id: string }} payload
 * @returns {Promise<{ share_url: string }>}
 */
export const createShareLink = (payload) =>
  post("/share/create", payload);

// ── Session ───────────────────────────────────────────────────────────────────

/**
 * Retrieve an existing session's data (e.g. after page reload).
 * @param {string} sessionId
 * @returns {Promise<object>}
 */
export const getSession = (sessionId) =>
  get(`/kundli/session/${sessionId}`);
