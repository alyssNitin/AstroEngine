/**
 * src/components/kundli/ReadingResultStep.jsx — Reading results + Q&A chat
 * ==========================================================================
 * Shows the refined reading text and an interactive Q&A chat panel.
 * Also provides email-report, download-report, career, compatibility actions.
 *
 * SOLID Notes
 * -----------
 * SRP : Manages only the reading display and Q&A interaction.
 * DIP : Uses kundliApi abstraction and SessionContext.
 * OCP : New action buttons can be added without changing existing code.
 */
import React, { useRef, useState } from "react";
import Card         from "../ui/Card.jsx";
import Button       from "../ui/Button.jsx";
import ErrorMessage from "../ui/ErrorMessage.jsx";
import Spinner      from "../ui/Spinner.jsx";
import { useSession } from "../../context/SessionContext.jsx";
import { useWallet  } from "../../context/WalletContext.jsx";
import { askQuestion, emailReport, downloadReport } from "../../api/kundliApi.js";

export default function ReadingResultStep() {
  const { session, appendQA }       = useSession();
  const { refresh: refreshWallet }  = useWallet();
  const { refinedReading, sessionId, qaHistory, birthDetails } = session;

  const [question,  setQuestion]  = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaError,   setQaError]   = useState(null);
  const [actionMsg, setActionMsg] = useState(null);
  const chatEndRef                = useRef(null);

  // ── Ask a question ──────────────────────────────────────────────────────────
  async function handleAsk() {
    if (!question.trim()) return;
    const q = question.trim();
    setQuestion("");
    setQaError(null);
    appendQA("user", q);
    setQaLoading(true);
    try {
      const data = await askQuestion({ session_id: sessionId, question: q });
      appendQA("assistant", data.answer);
      refreshWallet(); // credits may have changed
    } catch (err) {
      setQaError(err.detail ?? "Failed to get an answer. Please try again.");
    } finally {
      setQaLoading(false);
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  }

  // ── Email report ────────────────────────────────────────────────────────────
  async function handleEmailReport() {
    setActionMsg(null);
    try {
      await emailReport({ session_id: sessionId });
      setActionMsg({ text: "✅ Report sent to your email!", type: "success" });
    } catch (err) {
      setActionMsg({ text: err.detail ?? "Failed to email report.", type: "error" });
    }
  }

  // ── Download report ─────────────────────────────────────────────────────────
  async function handleDownload(format) {
    try {
      const blob = await downloadReport(sessionId, format);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `NarayanAstro_${birthDetails?.name ?? "reading"}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setActionMsg({ text: err.message ?? "Download failed.", type: "error" });
    }
  }

  return (
    <div className="animate-fade-in">
      {/* Heading */}
      <div style={{ textAlign: "center", marginBottom: "28px" }}>
        <h2 style={{ fontFamily: "var(--font-heading)", fontSize: "26px", color: "var(--brand-gold)", marginBottom: "8px" }}>
          📜 Your Vedic Reading
        </h2>
        <p style={{ color: "var(--text-secondary)" }}>
          For {birthDetails?.name ?? "you"} · {birthDetails?.dob} · {birthDetails?.city}, {birthDetails?.country}
        </p>
      </div>

      {/* Action message */}
      {actionMsg && (
        <ErrorMessage message={actionMsg.text} type={actionMsg.type} />
      )}

      {/* Reading text */}
      <Card glow style={{ marginBottom: "24px" }}>
        <Card.Header>
          <h3 style={{ fontFamily: "var(--font-heading)", fontSize: "18px", color: "var(--brand-purple-light)" }}>
            🌟 Deep Reading
          </h3>
        </Card.Header>
        <div
          style={{
            color:      "var(--text-primary)",
            lineHeight: "1.85",
            fontSize:   "15px",
            whiteSpace: "pre-wrap",
          }}
        >
          {refinedReading || <span style={{ color: "var(--text-muted)" }}>No reading available.</span>}
        </div>
      </Card>

      {/* Q&A Chat panel */}
      <Card style={{ marginBottom: "24px" }}>
        <Card.Header>
          <h3 style={{ fontFamily: "var(--font-heading)", fontSize: "18px", color: "var(--brand-purple-light)" }}>
            💬 Ask the AI Jyotish
          </h3>
          <p style={{ color: "var(--text-muted)", fontSize: "12px", marginTop: "4px" }}>
            Each question uses credits from your wallet.
          </p>
        </Card.Header>

        {/* Chat history */}
        <div
          style={{
            maxHeight:    "400px",
            overflowY:    "auto",
            padding:      "4px 0",
            marginBottom: "16px",
          }}
        >
          {qaHistory.length === 0 && (
            <p style={{ color: "var(--text-muted)", textAlign: "center", padding: "24px", fontSize: "14px" }}>
              Ask any question about your reading, your chart, or your life path…
            </p>
          )}
          {qaHistory.map((msg, i) => (
            <ChatBubble key={i} role={msg.role} content={msg.content} />
          ))}
          {qaLoading && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "12px 0", color: "var(--text-muted)", fontSize: "13px" }}>
              <Spinner size={18} /> The Jyotish is pondering…
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <ErrorMessage message={qaError} />

        {/* Chat input */}
        <div style={{ display: "flex", gap: "8px" }}>
          <input
            type="text"
            placeholder="Ask about career, relationships, health, timing…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAsk()}
            disabled={qaLoading}
            style={{
              flex:         1,
              padding:      "10px 14px",
              background:   "rgba(255,255,255,0.06)",
              border:       "1.5px solid var(--surface-border)",
              borderRadius: "var(--radius-md)",
              color:        "var(--text-primary)",
              fontSize:     "14px",
              outline:      "none",
            }}
          />
          <Button onClick={handleAsk} loading={qaLoading} disabled={!question.trim()}>
            Ask
          </Button>
        </div>
      </Card>

      {/* Report actions */}
      <Card padded={false} style={{ padding: "20px 24px" }}>
        <h3 style={{ fontFamily: "var(--font-heading)", fontSize: "16px", color: "var(--text-primary)", marginBottom: "14px" }}>
          📁 Your Report
        </h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
          <Button variant="secondary" onClick={handleEmailReport}>
            📧 Email Report
          </Button>
          <Button variant="ghost" onClick={() => handleDownload("pdf")}>
            ⬇️ Download PDF
          </Button>
          <Button variant="ghost" onClick={() => handleDownload("txt")}>
            ⬇️ Download Text
          </Button>
        </div>
      </Card>
    </div>
  );
}

// ── ChatBubble sub-component ────────────────────────────────────────────────

function ChatBubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div
      className="animate-fade-in"
      style={{
        display:        "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom:   "10px",
      }}
    >
      <div
        style={{
          maxWidth:     "80%",
          padding:      "10px 14px",
          borderRadius: isUser
            ? "var(--radius-md) var(--radius-md) 4px var(--radius-md)"
            : "var(--radius-md) var(--radius-md) var(--radius-md) 4px",
          background:   isUser ? "var(--brand-purple)" : "var(--surface-elevated)",
          color:        "var(--text-primary)",
          fontSize:     "14px",
          lineHeight:   "1.65",
          whiteSpace:   "pre-wrap",
        }}
      >
        {!isUser && (
          <span style={{ fontSize: "11px", color: "var(--brand-gold)", fontWeight: "600", display: "block", marginBottom: "4px" }}>
            🔮 AI Jyotish
          </span>
        )}
        {content}
      </div>
    </div>
  );
}
