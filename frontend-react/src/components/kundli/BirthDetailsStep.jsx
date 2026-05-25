/**
 * src/components/kundli/BirthDetailsStep.jsx — Birth details form step
 * ======================================================================
 * Collects name, date of birth, time of birth, city, country, gender,
 * language preference, and report type.
 * On submit calls /kundli/start and transitions to CHART step.
 *
 * SOLID Notes
 * -----------
 * SRP : Manages birth-details form state and the /kundli/start call.
 * DIP : Uses kundliApi abstraction and SessionContext.
 */
import React, { useState } from "react";
import Card         from "../ui/Card.jsx";
import Input, { Select } from "../ui/Input.jsx";
import Button       from "../ui/Button.jsx";
import ErrorMessage from "../ui/ErrorMessage.jsx";
import { useSession, STEPS } from "../../context/SessionContext.jsx";
import { useAuth }     from "../../context/AuthContext.jsx";
import { useLanguage } from "../../context/LanguageContext.jsx";
import { startReading } from "../../api/kundliApi.js";

// Values must match the language strings the AI backend accepts.
// All 9 Indian languages are available regardless of the UI language.
const LANGUAGE_OPTIONS = [
  { value: "English",   label: "English" },
  { value: "Hindi",     label: "हिंदी (Hindi)" },
  { value: "Tamil",     label: "தமிழ் (Tamil)" },
  { value: "Telugu",    label: "తెలుగు (Telugu)" },
  { value: "Bengali",   label: "বাংলা (Bengali)" },
  { value: "Marathi",   label: "मराठी (Marathi)" },
  { value: "Gujarati",  label: "ગુજરાતી (Gujarati)" },
  { value: "Kannada",   label: "ಕನ್ನಡ (Kannada)" },
  { value: "Malayalam", label: "മലയാളം (Malayalam)" },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function BirthDetailsStep() {
  const { user }                    = useAuth();
  const { updateSession, goToStep } = useSession();
  const { t, readingLanguage }      = useLanguage();

  // Gender and report type options are translated at render time via t()
  const genderOptions = [
    { value: "male",   label: t("male")   },
    { value: "female", label: t("female") },
    { value: "other",  label: t("other")  },
  ];

  const reportTypeOptions = [
    { value: "comprehensive", label: t("reportComprehensive") },
    { value: "career",        label: t("reportCareer")        },
    { value: "relationships", label: t("reportRelationships") },
    { value: "health",        label: t("reportHealth")        },
    { value: "spiritual",     label: t("reportSpiritual")     },
  ];

  const [form, setForm] = useState({
    name:        user?.name ?? "",
    dob:         "",
    tob:         "",
    city:        "",
    country:     "",
    gender:      "male",
    // Default reading language follows the UI language selection
    language:    readingLanguage,
    report_type: "comprehensive",
  });
  const [error,   setError]   = useState(null);
  const [loading, setLoading] = useState(false);

  const set = (field) => (e) => setForm((p) => ({ ...p, [field]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (!form.name.trim())    return setError(t("nameRequired"));
    if (!form.dob)            return setError(t("dateOfBirth") + " " + t("emailRequired").slice(-1));
    if (!form.tob)            return setError(t("timeOfBirth") + " required.");
    if (!form.city.trim())    return setError(t("placeOfBirth") + " required.");

    setLoading(true);
    try {
      const data = await startReading({
        name:        form.name.trim(),
        date_of_birth:  form.dob,
        time_of_birth:  form.tob,
        place_of_birth: `${form.city.trim()}, ${form.country.trim()}`,
        gender:      form.gender,
        language:    form.language,
        report_type: form.report_type,
        email:       user?.email ?? "",
      });

      updateSession({
        sessionId:    data.session_id,
        birthDetails: form,
        // Backend returns lagna / birth_info (not kundli_chart / dasha_data)
        kundliChart:  data.lagna      ?? data.kundli_chart ?? null,
        dashaData:    data.birth_info  ?? data.dasha_data   ?? null,
        predictions:  (data.predictions ?? []).map((p, i) => ({
          // Backend prediction shape: {id, statement, category, emoji, question}
          id:         p.id       ?? String(i),
          text:       p.statement ?? p.text ?? (typeof p === "string" ? p : ""),
          category:   p.category ?? "",
          emoji:      p.emoji    ?? "🔮",
          question:   p.question ?? "",
          confirmed:  null,
          correction: "",
        })),
      });

      goToStep(STEPS.CHART);
    } catch (err) {
      setError(err.detail ?? t("genericError"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="animate-fade-in">
      {/* Section heading */}
      <div style={{ textAlign: "center", marginBottom: "32px" }}>
        <h2
          style={{
            fontFamily:   "var(--font-heading)",
            fontSize:     "26px",
            color:        "var(--brand-gold)",
            marginBottom: "8px",
          }}
        >
          ✨ {t("birthDetails")}
        </h2>
        <p style={{ color: "var(--text-secondary)" }}>
          {t("readingHint")}
        </p>
      </div>

      <Card glow>
        <form onSubmit={handleSubmit} noValidate>
          <ErrorMessage message={error} />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
            {/* Name */}
            <div style={{ gridColumn: "1 / -1" }}>
              <Input
                label={t("name")}
                id="bd-name"
                type="text"
                placeholder="Arjuna Sharma"
                value={form.name}
                onChange={set("name")}
                required
              />
            </div>

            {/* Date + Time of birth */}
            <Input
              label={t("dateOfBirth")}
              id="bd-dob"
              type="date"
              value={form.dob}
              onChange={set("dob")}
              required
            />
            <Input
              label={t("timeOfBirth")}
              id="bd-tob"
              type="time"
              value={form.tob}
              onChange={set("tob")}
              required
            />

            {/* Place of birth — full width */}
            <div style={{ gridColumn: "1 / -1" }}>
              <Input
                label={t("placeOfBirth")}
                id="bd-city"
                type="text"
                placeholder="Mumbai, India"
                value={form.city}
                onChange={set("city")}
                required
              />
            </div>

            {/* Gender */}
            <Select
              label={t("gender")}
              id="bd-gender"
              options={genderOptions}
              value={form.gender}
              onChange={set("gender")}
            />

            {/* Reading language — always shows all 9 languages */}
            <Select
              label={t("language")}
              id="bd-language"
              options={LANGUAGE_OPTIONS}
              value={form.language}
              onChange={set("language")}
            />

            {/* Report type — full width */}
            <div style={{ gridColumn: "1 / -1" }}>
              <Select
                label={t("reportType")}
                id="bd-report-type"
                options={reportTypeOptions}
                value={form.report_type}
                onChange={set("report_type")}
              />
            </div>
          </div>

          <Button
            type="submit"
            fullWidth
            loading={loading}
            style={{ marginTop: "8px", padding: "14px" }}
          >
            🔮 {t("getMyReading")}
          </Button>
        </form>
      </Card>

      <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "12px", marginTop: "20px" }}>
        🔒 Your data is encrypted and used only to generate your reading.
      </p>
    </div>
  );
}
