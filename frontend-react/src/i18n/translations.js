/**
 * src/i18n/translations.js — UI string translations
 * ====================================================
 * Supports three languages as per the SRS:
 *   en  — English (default)
 *   hi  — Hindi  (हिंदी)
 *   ta  — Tamil  (தமிழ்)
 *
 * SOLID Notes
 * -----------
 * OCP : Add a new language by adding one object here — zero other changes.
 * SRP : Pure data — no components, no logic.
 *
 * Usage (via LanguageContext):
 *   const { t } = useLanguage();
 *   t("signIn")  // → "साइन इन करें" when lang === "hi"
 */

// ── English ───────────────────────────────────────────────────────────────────
const en = {
  // ── Auth ──────────────────────────────────────────────────────────────────
  signIn:              "Sign In",
  createAccount:       "Create Account",
  emailAddress:        "Email address",
  password:            "Password",
  confirmPassword:     "Confirm password",
  forgotPassword:      "Forgot password?",
  fullName:            "Full name",
  regionCurrency:      "Region / currency",
  resendVerification:  "Didn't receive it? Resend",
  verificationSent:    "Account created! Check your inbox for a verification link.",
  backToLogin:         "Back to Sign In",
  resetPassword:       "Reset Password",
  sendResetLink:       "Send Reset Link",
  newPassword:         "New password",
  setNewPassword:      "Set New Password",
  orSignInWith:        "Or sign in with",

  // ── Common actions ────────────────────────────────────────────────────────
  signOut:   "Sign out",
  loading:   "Loading…",
  submit:    "Submit",
  cancel:    "Cancel",
  send:      "Send",
  back:      "Back",
  confirm:   "Confirm",
  save:      "Save",
  close:     "Close",
  download:  "Download",
  emailReport: "Email Report",

  // ── Header / navigation ───────────────────────────────────────────────────
  navBrand:     "NarayanAstroReader",
  wallet:       "Wallet",
  topUp:        "Top Up",
  balance:      "Balance",
  signOutConfirmTitle: "Sign out?",
  signOutConfirmBody:  "Your current reading session will be lost. Are you sure?",

  // ── Birth details form ────────────────────────────────────────────────────
  birthDetails:  "Birth Details",
  name:          "Full name",
  dateOfBirth:   "Date of birth",
  timeOfBirth:   "Time of birth",
  placeOfBirth:  "Place of birth (city, country)",
  gender:        "Gender",
  male:          "Male",
  female:        "Female",
  other:         "Other / Prefer not to say",
  language:      "Language for reading",
  reportType:    "Report type",
  getMyReading:  "Get My Reading",
  readingHint:   "Your personalized Vedic astrology reading will be generated in the language you select.",

  // ── Report types ──────────────────────────────────────────────────────────
  reportComprehensive: "Comprehensive Reading",
  reportCareer:        "Career & Profession",
  reportRelationships: "Love & Relationships",
  reportHealth:        "Health & Wellness",
  reportSpiritual:     "Spiritual Path",

  // ── Reading flow ──────────────────────────────────────────────────────────
  predictions:       "Predictions",
  reading:           "Reading",
  refining:          "Refining your reading…",
  askQuestion:       "Ask Jyotishi a question…",
  sendQuestion:      "Send",
  confirmPrediction: "Confirm",
  correctPrediction: "Correct",
  enterCorrection:   "Enter correction…",
  noReadingYet:      "Your reading will appear here.",
  generatingReading: "Generating your reading…",
  chartLoading:      "Computing your Kundli chart…",
  downloadPdf:       "Download PDF",
  downloadTxt:       "Download Text",
  shareReading:      "Share Reading",
  readingReady:      "Your reading is ready!",
  jyotishiTyping:    "Jyotishi is thinking…",

  // ── Wallet modal ──────────────────────────────────────────────────────────
  walletTitle:       "Your Wallet",
  availableBalance:  "Available Balance",
  choosePackage:     "Choose a Top-Up Package",
  payNow:            "Pay Now",
  transactionHistory:"Transaction History",

  // ── Errors ────────────────────────────────────────────────────────────────
  emailRequired:       "Please enter your email address.",
  passwordRequired:    "Please enter your password.",
  nameRequired:        "Please enter your full name.",
  passwordTooShort:    "Password must be at least 8 characters.",
  passwordMismatch:    "Passwords do not match.",
  invalidCredentials:  "Incorrect email or password.",
  unverifiedEmail:     "Please verify your email before logging in. Check your inbox.",
  loginFailed:         "Login failed. Please try again.",
  registerFailed:      "Registration failed. Please try again.",
  emailTaken:          "An account with this email already exists. Try logging in.",
  genericError:        "Something went wrong. Please try again.",
  insufficientBalance: "Insufficient wallet balance. Please top up.",
};

// ── Hindi ─────────────────────────────────────────────────────────────────────
const hi = {
  // ── Auth ──────────────────────────────────────────────────────────────────
  signIn:             "साइन इन करें",
  createAccount:      "खाता बनाएं",
  emailAddress:       "ईमेल पता",
  password:           "पासवर्ड",
  confirmPassword:    "पासवर्ड की पुष्टि करें",
  forgotPassword:     "पासवर्ड भूल गए?",
  fullName:           "पूरा नाम",
  regionCurrency:     "क्षेत्र / मुद्रा",
  resendVerification: "नहीं मिला? पुनः भेजें",
  verificationSent:   "खाता बनाया गया! सत्यापन लिंक के लिए अपना इनबॉक्स देखें।",
  backToLogin:        "साइन इन पर वापस जाएं",
  resetPassword:      "पासवर्ड रीसेट करें",
  sendResetLink:      "रीसेट लिंक भेजें",
  newPassword:        "नया पासवर्ड",
  setNewPassword:     "नया पासवर्ड सेट करें",
  orSignInWith:       "या साइन इन करें",

  // ── Common actions ────────────────────────────────────────────────────────
  signOut:   "साइन आउट",
  loading:   "लोड हो रहा है…",
  submit:    "जमा करें",
  cancel:    "रद्द करें",
  send:      "भेजें",
  back:      "वापस",
  confirm:   "पुष्टि करें",
  save:      "सहेजें",
  close:     "बंद करें",
  download:  "डाउनलोड करें",
  emailReport: "रिपोर्ट ईमेल करें",

  // ── Header / navigation ───────────────────────────────────────────────────
  navBrand:     "NarayanAstroReader",
  wallet:       "वॉलेट",
  topUp:        "टॉप अप",
  balance:      "बैलेंस",
  signOutConfirmTitle: "साइन आउट करें?",
  signOutConfirmBody:  "आपका वर्तमान रीडिंग सत्र खो जाएगा। क्या आप सुनिश्चित हैं?",

  // ── Birth details form ────────────────────────────────────────────────────
  birthDetails:  "जन्म विवरण",
  name:          "पूरा नाम",
  dateOfBirth:   "जन्म तिथि",
  timeOfBirth:   "जन्म समय",
  placeOfBirth:  "जन्म स्थान (शहर, देश)",
  gender:        "लिंग",
  male:          "पुरुष",
  female:        "महिला",
  other:         "अन्य",
  language:      "रीडिंग की भाषा",
  reportType:    "रिपोर्ट प्रकार",
  getMyReading:  "मेरी कुंडली देखें",
  readingHint:   "आपकी व्यक्तिगत वैदिक ज्योतिष रीडिंग चयनित भाषा में तैयार की जाएगी।",

  // ── Report types ──────────────────────────────────────────────────────────
  reportComprehensive: "सम्पूर्ण रीडिंग",
  reportCareer:        "करियर और पेशा",
  reportRelationships: "प्रेम और रिश्ते",
  reportHealth:        "स्वास्थ्य और तंदुरुस्ती",
  reportSpiritual:     "आध्यात्मिक पथ",

  // ── Reading flow ──────────────────────────────────────────────────────────
  predictions:       "भविष्यवाणियाँ",
  reading:           "रीडिंग",
  refining:          "आपकी रीडिंग परिष्कृत हो रही है…",
  askQuestion:       "ज्योतिषी से प्रश्न पूछें…",
  sendQuestion:      "भेजें",
  confirmPrediction: "पुष्टि करें",
  correctPrediction: "सुधारें",
  enterCorrection:   "सुधार दर्ज करें…",
  noReadingYet:      "आपकी रीडिंग यहाँ दिखेगी।",
  generatingReading: "आपकी रीडिंग तैयार हो रही है…",
  chartLoading:      "आपकी कुंडली की गणना हो रही है…",
  downloadPdf:       "PDF डाउनलोड करें",
  downloadTxt:       "टेक्स्ट डाउनलोड करें",
  shareReading:      "रीडिंग साझा करें",
  readingReady:      "आपकी रीडिंग तैयार है!",
  jyotishiTyping:    "ज्योतिषी सोच रहे हैं…",

  // ── Wallet modal ──────────────────────────────────────────────────────────
  walletTitle:        "आपका वॉलेट",
  availableBalance:   "उपलब्ध बैलेंस",
  choosePackage:      "टॉप-अप पैकेज चुनें",
  payNow:             "अभी भुगतान करें",
  transactionHistory: "लेनदेन इतिहास",

  // ── Errors ────────────────────────────────────────────────────────────────
  emailRequired:       "कृपया अपना ईमेल पता दर्ज करें।",
  passwordRequired:    "कृपया अपना पासवर्ड दर्ज करें।",
  nameRequired:        "कृपया अपना पूरा नाम दर्ज करें।",
  passwordTooShort:    "पासवर्ड कम से कम 8 अक्षरों का होना चाहिए।",
  passwordMismatch:    "पासवर्ड मेल नहीं खाते।",
  invalidCredentials:  "गलत ईमेल या पासवर्ड।",
  unverifiedEmail:     "साइन इन करने से पहले अपना ईमेल सत्यापित करें।",
  loginFailed:         "लॉगिन विफल हुआ। कृपया पुनः प्रयास करें।",
  registerFailed:      "पंजीकरण विफल हुआ। कृपया पुनः प्रयास करें।",
  emailTaken:          "इस ईमेल से पहले से खाता मौजूद है।",
  genericError:        "कुछ गलत हो गया। कृपया पुनः प्रयास करें।",
  insufficientBalance: "अपर्याप्त वॉलेट बैलेंस। कृपया टॉप अप करें।",
};

// ── Tamil ─────────────────────────────────────────────────────────────────────
const ta = {
  // ── Auth ──────────────────────────────────────────────────────────────────
  signIn:             "உள்நுழைக",
  createAccount:      "கணக்கு உருவாக்கு",
  emailAddress:       "மின்னஞ்சல் முகவரி",
  password:           "கடவுச்சொல்",
  confirmPassword:    "கடவுச்சொல்லை உறுதிப்படுத்தவும்",
  forgotPassword:     "கடவுச்சொல் மறந்துவிட்டீர்களா?",
  fullName:           "முழு பெயர்",
  regionCurrency:     "பகுதி / நாணயம்",
  resendVerification: "கிடைக்கவில்லையா? மீண்டும் அனுப்பு",
  verificationSent:   "கணக்கு உருவாக்கப்பட்டது! உங்கள் மின்னஞ்சலை சரிபார்க்கவும்.",
  backToLogin:        "உள்நுழைவுக்கு திரும்பு",
  resetPassword:      "கடவுச்சொல் மீட்டமை",
  sendResetLink:      "மீட்டமை இணைப்பை அனுப்பு",
  newPassword:        "புதிய கடவுச்சொல்",
  setNewPassword:     "புதிய கடவுச்சொல் அமை",
  orSignInWith:       "அல்லது இதன் மூலம் உள்நுழைக",

  // ── Common actions ────────────────────────────────────────────────────────
  signOut:   "வெளியேறு",
  loading:   "ஏற்றுகிறது…",
  submit:    "சமர்ப்பி",
  cancel:    "ரத்துசெய்",
  send:      "அனுப்பு",
  back:      "திரும்பு",
  confirm:   "உறுதிப்படுத்து",
  save:      "சேமி",
  close:     "மூடு",
  download:  "பதிவிறக்கம்",
  emailReport: "அறிக்கையை மின்னஞ்சல் செய்",

  // ── Header / navigation ───────────────────────────────────────────────────
  navBrand:     "NarayanAstroReader",
  wallet:       "பணப்பை",
  topUp:        "நிரப்பு",
  balance:      "இருப்பு",
  signOutConfirmTitle: "வெளியேற விரும்புகிறீர்களா?",
  signOutConfirmBody:  "உங்கள் தற்போதைய வாசிப்பு அமர்வு இழக்கப்படும். நிச்சயமா?",

  // ── Birth details form ────────────────────────────────────────────────────
  birthDetails:  "பிறப்பு விவரங்கள்",
  name:          "முழு பெயர்",
  dateOfBirth:   "பிறந்த தேதி",
  timeOfBirth:   "பிறந்த நேரம்",
  placeOfBirth:  "பிறந்த இடம் (நகரம், நாடு)",
  gender:        "பாலினம்",
  male:          "ஆண்",
  female:        "பெண்",
  other:         "மற்றவை",
  language:      "வாசிப்பிற்கான மொழி",
  reportType:    "அறிக்கை வகை",
  getMyReading:  "என் ஜோதிடம் பெறுக",
  readingHint:   "நீங்கள் தேர்ந்தெடுக்கும் மொழியில் உங்கள் ஜோதிடம் தயாரிக்கப்படும்.",

  // ── Report types ──────────────────────────────────────────────────────────
  reportComprehensive: "விரிவான வாசிப்பு",
  reportCareer:        "தொழில் மற்றும் வாழ்க்கை",
  reportRelationships: "காதல் மற்றும் உறவுகள்",
  reportHealth:        "உடல் நலம் மற்றும் ஆரோக்கியம்",
  reportSpiritual:     "ஆன்மீக பாதை",

  // ── Reading flow ──────────────────────────────────────────────────────────
  predictions:       "கணிப்புகள்",
  reading:           "ஜோதிடம்",
  refining:          "உங்கள் வாசிப்பு செம்மைப்படுத்தப்படுகிறது…",
  askQuestion:       "ஜோதிடரிடம் கேளுங்கள்…",
  sendQuestion:      "அனுப்பு",
  confirmPrediction: "உறுதிப்படுத்து",
  correctPrediction: "திருத்து",
  enterCorrection:   "திருத்தம் உள்ளிடவும்…",
  noReadingYet:      "உங்கள் ஜோதிடம் இங்கே தோன்றும்.",
  generatingReading: "உங்கள் ஜோதிடம் தயாரிக்கப்படுகிறது…",
  chartLoading:      "உங்கள் கோச்சாரம் கணிக்கப்படுகிறது…",
  downloadPdf:       "PDF பதிவிறக்கம்",
  downloadTxt:       "உரை பதிவிறக்கம்",
  shareReading:      "வாசிப்பை பகிர்",
  readingReady:      "உங்கள் ஜோதிடம் தயார்!",
  jyotishiTyping:    "ஜோதிடர் சிந்திக்கிறார்…",

  // ── Wallet modal ──────────────────────────────────────────────────────────
  walletTitle:        "உங்கள் பணப்பை",
  availableBalance:   "கிடைக்கக்கூடிய இருப்பு",
  choosePackage:      "நிரப்பு தொகுப்பை தேர்ந்தெடுக்கவும்",
  payNow:             "இப்போது செலுத்து",
  transactionHistory: "பரிவர்த்தனை வரலாறு",

  // ── Errors ────────────────────────────────────────────────────────────────
  emailRequired:       "உங்கள் மின்னஞ்சல் முகவரியை உள்ளிடவும்.",
  passwordRequired:    "உங்கள் கடவுச்சொல்லை உள்ளிடவும்.",
  nameRequired:        "உங்கள் முழு பெயரை உள்ளிடவும்.",
  passwordTooShort:    "கடவுச்சொல் குறைந்தது 8 எழுத்துகளாக இருக்க வேண்டும்.",
  passwordMismatch:    "கடவுச்சொற்கள் பொருந்தவில்லை.",
  invalidCredentials:  "தவறான மின்னஞ்சல் அல்லது கடவுச்சொல்.",
  unverifiedEmail:     "உள்நுழைவதற்கு முன் உங்கள் மின்னஞ்சலை சரிபார்க்கவும்.",
  loginFailed:         "உள்நுழைவு தோல்வியடைந்தது. மீண்டும் முயற்சிக்கவும்.",
  registerFailed:      "பதிவு தோல்வியடைந்தது. மீண்டும் முயற்சிக்கவும்.",
  emailTaken:          "இந்த மின்னஞ்சலில் ஏற்கனவே கணக்கு உள்ளது.",
  genericError:        "ஏதோ தவறு நடந்தது. மீண்டும் முயற்சிக்கவும்.",
  insufficientBalance: "பணப்பை இருப்பு போதுமானதாக இல்லை. நிரப்பவும்.",
};

// ── Export ────────────────────────────────────────────────────────────────────

/** All supported UI languages */
export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English",    nativeLabel: "English" },
  { code: "hi", label: "Hindi",      nativeLabel: "हिंदी" },
  { code: "ta", label: "Tamil",      nativeLabel: "தமிழ்" },
];

/**
 * Map from UI language code → reading language name expected by the backend AI.
 * The backend's language field is a full English name (e.g. "Hindi"), not an ISO code.
 */
export const UI_LANG_TO_READING_LANG = {
  en: "English",
  hi: "Hindi",
  ta: "Tamil",
};

/** All translations keyed by language code */
const translations = { en, hi, ta };

export default translations;
