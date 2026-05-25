/**
 * src/pages/ReadingPage.jsx — Main authenticated reading page
 * ============================================================
 * Orchestrates the multi-step reading flow:
 *   BIRTH → CHART (predictions) → REFINING (loading) → READING (results + Q&A)
 *
 * Each step is its own component; this page manages the step machine.
 *
 * SOLID Notes
 * -----------
 * SRP : Pure step-routing — no form logic or API calls live here.
 * DIP : Uses SessionContext and step components — not hardwired.
 * OCP : New steps can be added to the switch without modifying existing ones.
 */
import React from "react";
import { useSession, STEPS } from "../context/SessionContext.jsx";
import AppHeader from "../components/layout/AppHeader.jsx";

// ── Step components (lazy-imported inline here for brevity) ──────────────────
import BirthDetailsStep  from "../components/kundli/BirthDetailsStep.jsx";
import PredictionsStep   from "../components/kundli/PredictionsStep.jsx";
import RefiningStep      from "../components/kundli/RefiningStep.jsx";
import ReadingResultStep from "../components/kundli/ReadingResultStep.jsx";

export default function ReadingPage() {
  const { step } = useSession();

  function renderStep() {
    switch (step) {
      case STEPS.BIRTH:    return <BirthDetailsStep />;
      case STEPS.CHART:    return <PredictionsStep />;
      case STEPS.REFINING: return <RefiningStep />;
      case STEPS.READING:  return <ReadingResultStep />;
      default:             return <BirthDetailsStep />;
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <AppHeader />
      {/* B15: id="main-content" is the skip-link target (WCAG 2.4.1) */}
      <main
        id="main-content"
        aria-label="Reading flow"
        style={{
          flex:       1,
          maxWidth:   "900px",
          width:      "100%",
          margin:     "0 auto",
          padding:    "32px 16px 64px",
        }}
      >
        {renderStep()}
      </main>
    </div>
  );
}
