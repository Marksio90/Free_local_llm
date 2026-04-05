import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Models from "./pages/Models";
import GitHub from "./pages/GitHub";
import Knowledge from "./pages/Knowledge";
import Training from "./pages/Training";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/models" element={<Models />} />
        <Route path="/github" element={<GitHub />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/training" element={<Training />} />
      </Routes>
    </Layout>
  );
}
