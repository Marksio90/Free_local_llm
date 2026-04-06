import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  MessageSquare,
  LayoutDashboard,
  Github,
  BookOpen,
  Cpu,
  Zap,
  Brain,
  RefreshCw,
  Globe,
  ExternalLink,
  ChevronLeft,
  Menu,
} from "lucide-react";

const NAV = [
  { to: "/",          icon: MessageSquare, label: "Chat",        exact: true },
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/models",    icon: Cpu,           label: "Modele" },
  { to: "/sync",      icon: RefreshCw,     label: "Auto-Sync" },
  { to: "/intel",     icon: Globe,         label: "Web Intel" },
  { to: "/github",    icon: Github,        label: "GitHub" },
  { to: "/knowledge", icon: BookOpen,      label: "Wiedza" },
  { to: "/memory",    icon: Brain,         label: "Pamięć" },
  { to: "/training",  icon: Zap,           label: "Trening" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`bg-dark-800 border-r border-dark-500 flex flex-col transition-all duration-200 ${
          collapsed ? "w-14" : "w-56"
        }`}
      >
        {/* Header */}
        <div className={`border-b border-dark-500 flex items-center ${collapsed ? "px-3 py-4 justify-center" : "px-5 py-5 justify-between"}`}>
          {!collapsed && (
            <div>
              <div className="text-accent-400 font-bold text-sm tracking-widest uppercase">
                Free Local LLM
              </div>
              <div className="text-gray-500 text-xs mt-0.5">v3.0 – Personal AI</div>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="text-gray-500 hover:text-gray-300 transition-colors p-1 rounded"
            title={collapsed ? "Rozwiń panel" : "Zwiń panel"}
          >
            {collapsed ? <Menu size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-4 space-y-0.5">
          {NAV.map(({ to, icon: Icon, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors group ${
                  isActive
                    ? "bg-accent-500/20 text-accent-300 border border-accent-500/30"
                    : "text-gray-400 hover:text-gray-100 hover:bg-dark-600"
                }`
              }
              title={collapsed ? label : undefined}
            >
              <Icon size={16} className="shrink-0" />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Footer links */}
        {!collapsed && (
          <div className="px-3 py-4 border-t border-dark-500 space-y-0.5">
            <a
              href="http://localhost:11434"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 text-xs text-gray-500 hover:text-accent-300 transition-colors px-3 py-1.5"
            >
              <ExternalLink size={11} />
              Ollama API
            </a>
            <a
              href="http://localhost:8080/docs"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 text-xs text-gray-500 hover:text-accent-300 transition-colors px-3 py-1.5"
            >
              <ExternalLink size={11} />
              API Docs
            </a>
          </div>
        )}
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-dark-900">
        <div className="max-w-5xl mx-auto px-6 py-8">{children}</div>
      </main>
    </div>
  );
}
