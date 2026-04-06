import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import Models from "./pages/Models";
import GitHub from "./pages/GitHub";
import Knowledge from "./pages/Knowledge";
import Training from "./pages/Training";
import Memory from "./pages/Memory";
import Sync from "./pages/Sync";
import Intel from "./pages/Intel";

// Admin layout wrapper
function AdminLayout({ children }: { children: React.ReactNode }) {
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      {/* Primary: full-screen chat, no sidebar */}
      <Route path="/"          element={<Chat />} />

      {/* Admin / settings pages — wrapped in collapsible sidebar layout */}
      <Route path="/dashboard" element={<AdminLayout><Dashboard /></AdminLayout>} />
      <Route path="/models"    element={<AdminLayout><Models /></AdminLayout>} />
      <Route path="/sync"      element={<AdminLayout><Sync /></AdminLayout>} />
      <Route path="/github"    element={<AdminLayout><GitHub /></AdminLayout>} />
      <Route path="/knowledge" element={<AdminLayout><Knowledge /></AdminLayout>} />
      <Route path="/intel"     element={<AdminLayout><Intel /></AdminLayout>} />
      <Route path="/memory"    element={<AdminLayout><Memory /></AdminLayout>} />
      <Route path="/training"  element={<AdminLayout><Training /></AdminLayout>} />
    </Routes>
  );
}
