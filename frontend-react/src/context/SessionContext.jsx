/**
 * src/context/SessionContext.jsx — Kundli reading session state provider
 * ========================================================================
 * Tracks the in-progress reading session: birth details, predictions,
 * refined reading, Q&A history, and the current navigation step.
 *
 * Usage:
 *   const { session, setSession, step, goToStep, reset } = useSession();
 *
 * SOLID Notes
 * -----------
 * SRP : Manages only reading-session state, nothing about auth or wallet.
 * OCP : New session fields can be added without changing any existing consumers.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";

// ── Types / Initial State ─────────────────────────────────────────────────────

/**
 * Default empty session.
 * @type {SessionState}
 */
const INITIAL_SESSION = {
  sessionId:      null,   // string — returned by /kundli/start
  birthDetails:   null,   // { name, dob, tob, city, country, gender, language, reportType }
  kundliChart:    null,   // raw chart object from backend
  dashaData:      null,   // planetary periods data
  predictions:    [],     // Array<{ id, text, confirmed, correction? }>
  refinedReading: null,   // string — long-form reading after confirmations
  qaHistory:      [],     // Array<{ role: "user"|"assistant", content: string }>
  reportUrl:      null,   // shareable URL after report generation
  careerReport:   null,   // string
  compatReport:   null,   // string
};

/** Application navigation steps */
export const STEPS = {
  AUTH:       "auth",       // Login / register screen
  BIRTH:      "birth",      // Birth details form
  CHART:      "chart",      // Kundli chart + prediction confirmation
  REFINING:   "refining",   // Loading / refining state
  READING:    "reading",    // Refined reading + Q&A
  CAREER:     "career",     // Career report
  COMPAT:     "compat",     // Compatibility form + report
  SETTINGS:   "settings",   // Account / MFA / profiles
};

// ── Context ───────────────────────────────────────────────────────────────────

const SessionContext = createContext(null);

// ── Provider ──────────────────────────────────────────────────────────────────

/**
 * @param {{ children: React.ReactNode }} props
 */
export function SessionProvider({ children }) {
  const [session, setSession] = useState(INITIAL_SESSION);
  const [step,    setStep]    = useState(STEPS.AUTH);

  /** Merge partial updates into the session (like setState in class components) */
  const updateSession = useCallback((updates) => {
    setSession((prev) => ({ ...prev, ...updates }));
  }, []);

  /** Navigate to a named step */
  const goToStep = useCallback((stepName) => {
    setStep(stepName);
    // Scroll to top on navigation
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  /** Reset everything — called on logout or "start over" */
  const reset = useCallback(() => {
    setSession(INITIAL_SESSION);
    setStep(STEPS.AUTH);
  }, []);

  /** Append a message to the Q&A history */
  const appendQA = useCallback((role, content) => {
    setSession((prev) => ({
      ...prev,
      qaHistory: [...prev.qaHistory, { role, content, ts: Date.now() }],
    }));
  }, []);

  /** Mark a prediction as confirmed/rejected */
  const confirmPrediction = useCallback((id, confirmed, correction = "") => {
    setSession((prev) => ({
      ...prev,
      predictions: prev.predictions.map((p) =>
        p.id === id ? { ...p, confirmed, correction } : p,
      ),
    }));
  }, []);

  const value = {
    session,
    step,
    setSession,
    updateSession,
    goToStep,
    reset,
    appendQA,
    confirmPrediction,
  };

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * @returns {{
 *   session: SessionState,
 *   step: string,
 *   setSession: Function,
 *   updateSession: Function,
 *   goToStep: Function,
 *   reset: Function,
 *   appendQA: Function,
 *   confirmPrediction: Function,
 * }}
 */
export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}

export default SessionContext;
