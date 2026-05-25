/**
 * src/components/kundli/PredictionsStep.jsx — Prediction confirmation step
 * ==========================================================================
 * Shows the Kundli chart and a list of AI-generated predictions.
 * The user confirms or corrects each prediction, then submits to refine.
 *
 * SOLID Notes
 * -----------
 * SRP : Manages prediction UI state and the /kundli/refine call.
 */
import React, { useState } from "react";
import Card         from "../ui/Card.jsx";
import Button       from "../ui/Button.jsx";
import ErrorMessage from "../ui/ErrorMessage.jsx";
import { useSession, STEPS } from "../../context/SessionContext.jsx";
import { useAuth }           from "../../context/AuthContext.jsx";
import { refineReading }     from "../../api/kundliApi.js";

export default function PredictionsStep() {
  const { session, confirmPrediction, updateSession, goToStep } = useSession();
  const { user }            = useAuth();
  const { predictions, sessionId, birthDetails } = session;

  const [error,   setError]   = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    setError(null);
    const unreviewed = predictions.filter((p) => p.confirmed === null);
    if (unreviewed.length > 0) {
      return setError(`Please confirm or correct all ${unreviewed.length} remaining prediction(s).`);
    }

    setLoading(true);
    // Show the animated loading screen immediately — the SSE stream
    // may take 20–60 seconds, so we navigate to REFINING right away.
    goToStep(STEPS.REFINING);

    try {
      const data = await refineReading({
        session_id:    sessionId,
        confirmations: predictions.map((p) => ({
          id:         p.id,
          confirmed:  p.confirmed,
          correction: p.correction ?? "",
        })),
        // Pass auth context so the backend can write the reading to the DB
        email:    user?.email ?? "",
        language: birthDetails?.language ?? "English",
      });

      updateSession({ refinedReading: data.refined_reading ?? "" });
      goToStep(STEPS.READING);
    } catch (err) {
      setError(err.detail ?? "Refinement failed. Please try again.");
      goToStep(STEPS.CHART); // go back so user can retry
    } finally {
      setLoading(false);
    }
  }

  const confirmedCount = predictions.filter((p) => p.confirmed !== null).length;
  const progress = predictions.length > 0 ? (confirmedCount / predictions.length) * 100 : 0;

  return (
    <div className="animate-fade-in">
      <div style={{ textAlign: "center", marginBottom: "28px" }}>
        <h2 style={{ fontFamily: "var(--font-heading)", fontSize: "24px", color: "var(--brand-gold)", marginBottom: "8px" }}>
          🔭 Your Kundli Predictions
        </h2>
        <p style={{ color: "var(--text-secondary)" }}>
          Review each prediction — confirm those that resonate, or correct those that don't.
          This helps the AI personalise your deep reading.
        </p>
      </div>

      {/* Progress bar */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px", fontSize: "13px", color: "var(--text-secondary)" }}>
          <span>Progress</span>
          <span>{confirmedCount} / {predictions.length} reviewed</span>
        </div>
        <div style={{ height: "6px", background: "var(--surface-elevated)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
          <div
            style={{
              height:     "100%",
              width:      `${progress}%`,
              background: "linear-gradient(90deg, var(--brand-purple), var(--brand-gold))",
              borderRadius: "var(--radius-full)",
              transition: "width var(--transition-base)",
            }}
          />
        </div>
      </div>

      <ErrorMessage message={error} />

      {/* Prediction cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "24px" }}>
        {predictions.map((pred, i) => (
          <PredictionCard
            key={pred.id}
            index={i + 1}
            prediction={pred}
            onChange={confirmPrediction}
          />
        ))}
      </div>

      <Button
        fullWidth
        loading={loading}
        onClick={handleSubmit}
        style={{ padding: "14px" }}
      >
        ✨ Generate My Deep Reading →
      </Button>
    </div>
  );
}

// ── PredictionCard ─────────────────────────────────────────────────────────────

/**
 * @param {{
 *   index: number,
 *   prediction: { id: string, text: string, confirmed: boolean|null, correction: string },
 *   onChange: (id: string, confirmed: boolean, correction?: string) => void,
 * }} props
 */
function PredictionCard({ index, prediction, onChange }) {
  const [showCorrection, setShowCorrection] = useState(false);
  const [correction,     setCorrection]     = useState(prediction.correction ?? "");

  const isConfirmed  = prediction.confirmed === true;
  const isCorrected  = prediction.confirmed === false;
  const isUnreviewed = prediction.confirmed === null;

  function handleConfirm() {
    setShowCorrection(false);
    onChange(prediction.id, true, "");
  }

  function handleCorrect() {
    setShowCorrection(true);
  }

  function submitCorrection() {
    onChange(prediction.id, false, correction);
    setShowCorrection(false);
  }

  // Border/background based on state
  const borderColor = isConfirmed  ? "var(--color-success)" :
                      isCorrected  ? "var(--color-warning)" :
                                     "var(--surface-border)";

  return (
    <Card
      style={{
        border:     `1.5px solid ${borderColor}`,
        transition: "border-color var(--transition-base)",
      }}
    >
      {/* Category header */}
      {prediction.category && (
        <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "10px" }}>
          <span style={{ fontSize: "16px" }}>{prediction.emoji}</span>
          <span style={{ fontSize: "11px", fontWeight: "700", color: "var(--brand-gold)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            {prediction.category}
          </span>
          <span style={{ marginLeft: "auto", fontSize: "11px", color: "var(--text-muted)" }}>#{index}</span>
        </div>
      )}

      {/* Prediction statement */}
      <div style={{ display: "flex", gap: "12px", alignItems: "flex-start", marginBottom: prediction.question ? "10px" : "14px" }}>
        {!prediction.category && (
          <span style={{ flexShrink: 0, width: "28px", height: "28px", background: "var(--surface-elevated)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "12px", color: "var(--text-secondary)", fontWeight: "600" }}>
            {index}
          </span>
        )}
        <p style={{ color: "var(--text-primary)", lineHeight: "1.65", margin: 0, flex: 1 }}>
          {prediction.text}
        </p>
      </div>

      {/* Guiding question — helps user know what to confirm/correct */}
      {prediction.question && (
        <p style={{ color: "var(--text-muted)", fontSize: "13px", fontStyle: "italic", marginBottom: "14px", paddingLeft: "4px", borderLeft: "2px solid var(--surface-border)" }}>
          {prediction.question}
        </p>
      )}

      {/* Action buttons */}
      {!showCorrection ? (
        <div style={{ display: "flex", gap: "10px" }}>
          <Button
            variant={isConfirmed ? "primary" : "secondary"}
            onClick={handleConfirm}
            style={{ flex: 1, padding: "8px" }}
          >
            {isConfirmed ? "✓ Confirmed" : "✓ Confirm"}
          </Button>
          <Button
            variant={isCorrected ? "gold" : "ghost"}
            onClick={handleCorrect}
            style={{ flex: 1, padding: "8px" }}
          >
            {isCorrected ? "✏️ Corrected" : "✏️ Correct"}
          </Button>
        </div>
      ) : (
        /* Correction input */
        <div>
          <textarea
            placeholder="How does this differ from your experience? Describe the correction..."
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            rows={3}
            style={{
              width:        "100%",
              padding:      "10px 12px",
              background:   "rgba(255,255,255,0.05)",
              border:       "1.5px solid var(--brand-gold)",
              borderRadius: "var(--radius-md)",
              color:        "var(--text-primary)",
              fontSize:     "14px",
              resize:       "vertical",
              marginBottom: "10px",
              boxSizing:    "border-box",
            }}
          />
          <div style={{ display: "flex", gap: "10px" }}>
            <Button onClick={submitCorrection} style={{ flex: 1, padding: "8px" }}>
              Save Correction
            </Button>
            <Button
              variant="ghost"
              onClick={() => setShowCorrection(false)}
              style={{ flex: 1, padding: "8px" }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
