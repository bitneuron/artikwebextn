import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import Dashboard from "./pages/Dashboard";
import TemplatesGallery from "./pages/TemplatesGallery";
import CreateAgentWizard from "./pages/CreateAgentWizard";
import AgentDetails from "./pages/AgentDetails";
import RunHistory from "./pages/RunHistory";
import Settings from "./pages/Settings";
import UsersAdmin from "./pages/UsersAdmin";
import AuditLog from "./pages/AuditLog";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/templates" element={<TemplatesGallery />} />
          <Route path="/agents/new" element={<CreateAgentWizard mode="create" />} />
          <Route path="/agents/:id/edit" element={<CreateAgentWizard mode="edit" />} />
          <Route path="/agents/:id" element={<AgentDetails />} />
          <Route path="/runs" element={<RunHistory />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/users" element={<UsersAdmin />} />
          <Route path="/audit" element={<AuditLog />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
