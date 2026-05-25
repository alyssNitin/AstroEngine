/**
 * src/components/kundli/RefiningStep.jsx — Loading / refining screen
 * =====================================================================
 * Shown while the AI is generating the deep reading.
 * Displays animated cosmic progress messages to keep the user engaged.
 *
 * SOLID Notes
 * -----------
 * SRP : Pure UI state — no API calls or data mutations.
 */
import React, { useEffect, useState } from "react";
import Spinner from "../ui/Spinner.jsx";

const MESSAGES = [
  "🪐 Charting the planetary positions…",
  "🌙 Analysing your Lagna and Navamsha…",
  "⭐ Calculating Vimshottari Dasha periods…",
  "🔭 Consulting the ancient Jyotish texts…",
  "🌟 Weaving your personalised narrative…",
  "✨ Applying your corrections to refine…",
  "📜 Composing your deep reading…",
];

/** Cycle through wisdom messages every 2.5 seconds */
export default function RefiningStep() {
  const [msgIndex, setMsgIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setMsgIndex((i) => (i + 1) % MESSAGES.length);
    }, 2500);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className="animate-fade-in"
      style={{
        display:        "flex",
        flexDirection:  "column",
        alignItems:     "center",
        justifyContent: "center",
        minHeight:      "60vh",
        textAlign:      "center",
        padding:        "32px",
      }}
    >
      <Spinner size={72} />

      <h2
        style={{
          fontFamily: "var(--font-heading)",
          fontSize:   "22px",
          color:      "var(--brand-gold)",
          marginTop:  "32px",
          marginBottom: "12px",
        }}
      >
        Generating Your Deep Reading
      </h2>

      <p
        key={msgIndex}
        className="animate-fade-in"
        style={{
          color:     "var(--text-secondary)",
          fontSize:  "16px",
          maxWidth:  "400px",
          lineHeight: "1.6",
        }}
      >
        {MESSAGES[msgIndex]}
      </p>

      <p style={{ color: "var(--text-muted)", fontSize: "12px", marginTop: "24px" }}>
        This usually takes 20–60 seconds. Please don't close the tab.
      </p>
    </div>
  );
}
