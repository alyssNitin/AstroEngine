/**
 * src/App.jsx — Root application component + router
 * ====================================================
 * Sets up React Router v6 routes, wraps the tree with context providers,
 * and guards private routes.
 *
 * Route map
 * ---------
 *   /                → AuthPage    (login / register / forgot-password)
 *   /reading         → ReadingPage (protected — requires auth)
 *   /reset-password  → ResetPasswordPage
 *   *                → redirect to /
 *
 * SOLID Notes
 * -----------
 * SRP : App only defines providers and routes — no business logic.
 * DIP : Route guards read from AuthContext, not from localStorage directly.
 * OCP : Adding a new route/page requires one line here and a new page file.
 */
import React, { Suspense } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";

import { LanguageProvider } from "./context/LanguageContext.jsx";
import { AuthProvider }    from "./context/AuthContext.jsx";
import { WalletProvider }  from "./context/WalletContext.jsx";
import { SessionProvider } from "./context/SessionContext.jsx";
import { useAuth }         from "./context/AuthContext.jsx";

import Spinner             from "./components/ui/Spinner.jsx";
import AuthPage            from "./pages/AuthPage.jsx";
import ReadingPage         from "./pages/ReadingPage.jsx";
import ResetPasswordPage   from "./pages/ResetPasswordPage.jsx";

// ── Protected Route guard ─────────────────────────────────────────────────────

/**
 * Redirects unauthenticated users to "/" (login).
 * Shows a full-screen spinner while the auth state is being rehydrated.
 */
function RequireAuth({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) return <Spinner fullScreen message="Loading your session…" />;
  if (!isAuthenticated) return <Navigate to="/" replace />;
  return children;
}

// ── App router ────────────────────────────────────────────────────────────────

function AppRoutes() {
  return (
    <Suspense fallback={<Spinner fullScreen />}>
      <Routes>
        {/* Public routes */}
        <Route path="/"               element={<AuthPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        {/* Protected routes */}
        <Route
          path="/reading"
          element={
            <RequireAuth>
              <ReadingPage />
            </RequireAuth>
          }
        />

        {/* Catch-all → auth */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

// ── Root component — wraps everything in providers ────────────────────────────

/**
 * Provider order matters:
 *   LanguageProvider — outermost: auth forms and every other component need t()
 *   AuthProvider     — depends on nothing from context
 *   WalletProvider   — depends on isAuthenticated from AuthContext
 *   SessionProvider  — depends on nothing from context
 */
export default function App() {
  return (
    <BrowserRouter>
      <LanguageProvider>
        <AuthProvider>
          <WalletProvider>
            <SessionProvider>
              <AppRoutes />
            </SessionProvider>
          </WalletProvider>
        </AuthProvider>
      </LanguageProvider>
    </BrowserRouter>
  );
}
