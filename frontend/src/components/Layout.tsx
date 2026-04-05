import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Github,
  BookOpen,
  Cpu,
  Zap,
  ExternalLink,
} from "lucide-react";

const NAV = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/models", icon: Cpu, label: "Modele" },
  { to: "/github", icon: Github, label: "GitHub" },
  { to: "/knowledge", icon: BookOpen, label: "Wiedza" },
  { to: "/training", icon: Zap, label: "Trening" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 bg-dark-800 border-r border-dark-500 flex flex-col">
        <div className="px-5 py-5 border-b border-dark-500">
          <div className="text-accent-400 font-bold text-sm tracking-widest uppercase">
            Free Local LLM
          </div>
          <div className="text-gray-500 text-xs mt-0.5">Panel zarządzania</div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-accent-500/20 text-accent-300 border border-accent-500/30"
                    : "text-gray-400 hover:text-gray-100 hover:bg-dark-600"
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-dark-500 space-y-2">
          <a
            href="http://localhost:3000"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 text-xs text-gray-500 hover:text-accent-300 transition-colors px-3 py-2"
          >
            <ExternalLink size={12} />
            Open WebUI (czat)
          </a>
          <a
            href="http://localhost:8080/docs"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 text-xs text-gray-500 hover:text-accent-300 transition-colors px-3 py-2"
          >
            <ExternalLink size={12} />
            API Docs
          </a>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-dark-900">
        <div className="max-w-5xl mx-auto px-6 py-8">{children}</div>
      </main>
    </div>
  );
}
