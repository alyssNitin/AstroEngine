/**
 * src/context/LanguageContext.jsx — Global UI language provider
 * ==============================================================
 * Drives the language of all UI text (labels, buttons, errors) across
 * the entire application.  Supports English, Hindi, Tamil.
 *
 * Usage:
 *   const { lang, setLang, t } = useLanguage();
 *   t("signIn")          // → "साइन इन करें" when lang === "hi"
 *   t("missing_key")     // → "missing_key"  (transparent fallback)
 *
 * Language is persisted to localStorage so the choice survives page reloads.
 *
 * SOLID Notes
 * -----------
 * SRP  : Owns only UI-language state and lookup.
 * OCP  : New languages are added in translations.js — zero changes here.
 * DIP  : Components depend on useLanguage() hook, not on the translations
 *        object directly.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import translations, {
  SUPPORTED_LANGUAGES,
  UI_LANG_TO_READING_LANG,
} from "../i18n/translations.js";

// ── Storage key ───────────────────────────────────────────────────────────────
const LANG_KEY = "nar_ui_lang";

// ── Context ───────────────────────────────────────────────────────────────────
const LanguageContext = createContext(null);

// ── Provider ──────────────────────────────────────────────────────────────────

/**
 * @param {{ children: React.ReactNode }} props
 */
export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    // Restore from localStorage; fall back to "en"
    const stored = localStorage.getItem(LANG_KEY);
    return SUPPORTED_LANGUAGES.some((l) => l.code === stored) ? stored : "en";
  });

  // Persist choice whenever it changes
  useEffect(() => {
    localStorage.setItem(LANG_KEY, lang);
    // Set <html lang="..."> for accessibility and browser hinting
    document.documentElement.lang = lang;
  }, [lang]);

  /** Change the UI language */
  const setLang = useCallback((code) => {
    if (SUPPORTED_LANGUAGES.some((l) => l.code === code)) {
      setLangState(code);
    }
  }, []);

  /**
   * Translate a key to the current language.
   * Falls back to English, then to the raw key itself.
   * @param {string} key  — key from translations.js
   * @returns {string}
   */
  const t = useCallback(
    (key) =>
      translations[lang]?.[key] ??
      translations["en"]?.[key] ??
      key,
    [lang],
  );

  /**
   * The backend AI reading language corresponding to the current UI language.
   * e.g. when lang === "hi" → "Hindi"
   */
  const readingLanguage = UI_LANG_TO_READING_LANG[lang] ?? "English";

  const value = {
    lang,           // current language code: "en" | "hi" | "ta"
    setLang,        // (code: string) => void
    t,              // (key: string) => string
    readingLanguage, // full language name for the AI reading backend
    supportedLanguages: SUPPORTED_LANGUAGES,
  };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Access language state and translation helper.
 * Must be used inside <LanguageProvider>.
 *
 * @returns {{
 *   lang: string,
 *   setLang: (code: string) => void,
 *   t: (key: string) => string,
 *   readingLanguage: string,
 *   supportedLanguages: Array<{ code: string, label: string, nativeLabel: string }>,
 * }}
 */
export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used inside <LanguageProvider>");
  return ctx;
}

export default LanguageContext;
