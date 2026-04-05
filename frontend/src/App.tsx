import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import Models from "./pages/Models";
import GitHub from "./pages/GitHub";
import Knowledge from "./pages/Knowledge";
import Training from "./pages/Training";
import Memory from "./pages/Memory";
import Sync from "./pages/Sync";
import Intel from "./pages/Intel";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/"          element={<Dashboard />} />
        <Route path="/chat"      element={<Chat />} />
        <Route path="/models"    element={<Models />} />
        <Route path="/sync"      element={<Sync />} />
        <Route path="/github"    element={<GitHub />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/intel"     element={<Intel />} />
        <Route path="/memory"    element={<Memory />} />
        <Route path="/training"  element={<Training />} />
      </Routes>
    </Layout>
  );
}
