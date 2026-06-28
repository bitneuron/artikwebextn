import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import Dashboard from "./pages/Dashboard";
import Reminders from "./pages/Reminders";
import ReminderForm from "./pages/ReminderForm";
import ReminderDetail from "./pages/ReminderDetail";
import CalendarPage from "./pages/Calendar";
import Notifications from "./pages/Notifications";
import QuickNotes from "./pages/QuickNotes";
import Assistant from "./pages/Assistant";
import Admin from "./pages/Admin";
import Settings from "./pages/Settings";
import Platform from "./pages/Platform";

function Protected({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid h-screen place-items-center text-slate-400">Loading…</div>;
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  const { user } = useAuth();
  return (
    <Routes>
      {/* Cross-product landing — public */}
      <Route path="/platform" element={<Platform />} />
      <Route path="/apps" element={<Navigate to="/platform" replace />} />
      {/* URL aliases → this app's root (case handled by lowercasing in <Alias/>) */}
      {["/artiknotifier", "/ArtikNotifier", "/artik-notifier", "/notifier"].map((p) => (
        <Route key={p} path={p} element={<Navigate to="/" replace />} />
      ))}
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to="/" replace /> : <Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/reminders" element={<Reminders />} />
        <Route path="/reminders/new" element={<ReminderForm />} />
        <Route path="/reminders/:id" element={<ReminderDetail />} />
        <Route path="/reminders/:id/edit" element={<ReminderForm />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/notes" element={<QuickNotes />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
