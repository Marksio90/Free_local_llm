import { useEffect, useState } from "react";
import { api, CollectionInfo, ModelInfo } from "../api/client";
import { Cpu, BookOpen, Brain, ExternalLink, CheckCircle, XCircle, RefreshCw, MessageSquare } from "lucide-react";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8080";

export default function Dashboard() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [memStats, setMemStats] = useState<{ total_memories: number } | null>(null);
  const [syncStatus, setSyncStatus] = useState<{ repos_synced?: number; last_run?: string } | null>(null);

  useEffect(() => {
    api.health().then(() => setBackendOk(true)).catch(() => setBackendOk(false));
    api.models.list().then((r) => setModels(r.models ?? [])).catch(() => {});
    api.knowledge.collections().then(setCollections).catch(() => {});
    fetch(`${BASE}/api/memory/stats`).then((r) => r.json()).then(setMemStats).catch(() => {});
    fetch(`${BASE}/api/sync/status`).then((r) => r.json()).then(setSyncStatus).catch(() => {});
  }, []);

  const totalChunks = collections.reduce((s, c) => s + c.count, 0);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">Lokalne centrum AI – status systemu</p>
      </div>

      {/* Status */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
        <StatCard
          label="Backend"
          value={backendOk === null ? "..." : backendOk ? "Online" : "Offline"}
          icon={backendOk ? CheckCircle : XCircle}
          color={backendOk ? "text-green-400" : "text-red-400"}
        />
        <StatCard label="Modele" value={models.length} icon={Cpu} color="text-accent-400" />
        <StatCard label="Kolekcje" value={collections.length} icon={BookOpen} color="text-blue-400" />
        <StatCard label="Fragmenty kodu" value={totalChunks} icon={BookOpen} color="text-purple-400" />
        <StatCard label="Wspomnienia" value={memStats?.total_memories ?? "..."} icon={Brain} color="text-pink-400" />
        <StatCard label="Repo zsynced" value={syncStatus?.repos_synced ?? "—"} icon={RefreshCw} color="text-green-400" />
      </div>

      {/* Quick action */}
      <div className="card border-accent-500/20 bg-accent-500/5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-accent-300">Zacznij od razu</div>
            <p className="text-xs text-gray-400 mt-0.5">Chat automatycznie przeszuka Twoje repo i pamięć</p>
          </div>
          <a href="/chat" className="btn-primary flex items-center gap-2">
            <MessageSquare size={13} />
            Otwórz Chat
          </a>
        </div>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <QuickLink
          href="http://localhost:3000"
          title="Open WebUI"
          desc="Interfejs czatu z modelami"
          label="Otwórz czat"
        />
        <QuickLink
          href="http://localhost:8080/docs"
          title="API Docs"
          desc="Swagger UI – pełna dokumentacja REST API"
          label="Otwórz docs"
        />
        <QuickLink
          href="http://localhost:8001"
          title="ChromaDB"
          desc="Baza wektorowa – podgląd kolekcji"
          label="Otwórz ChromaDB"
        />
      </div>

      {/* Installed models */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Cpu size={14} className="text-accent-400" />
          Zainstalowane modele
        </h2>
        {models.length === 0 ? (
          <p className="text-gray-500 text-sm">Brak modeli. Pobierz model w zakładce Modele.</p>
        ) : (
          <div className="space-y-2">
            {models.map((m) => (
              <div key={m.name} className="flex items-center justify-between py-2 border-b border-dark-500 last:border-0">
                <span className="text-sm text-gray-200">{m.name}</span>
                <div className="flex items-center gap-3">
                  {m.details?.parameter_size && (
                    <span className="badge-blue">{m.details.parameter_size}</span>
                  )}
                  <span className="text-xs text-gray-500">
                    {m.size ? `${(m.size / 1e9).toFixed(1)} GB` : ""}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Collections */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <BookOpen size={14} className="text-blue-400" />
          Kolekcje wiedzy
        </h2>
        {collections.length === 0 ? (
          <p className="text-gray-500 text-sm">
            Brak danych. Zaingestionuj repo GitHub lub wgraj dokumenty w zakładce Wiedza.
          </p>
        ) : (
          <div className="space-y-2">
            {collections.map((c) => (
              <div key={c.name} className="flex items-center justify-between py-2 border-b border-dark-500 last:border-0">
                <span className="text-sm text-gray-200 font-mono">{c.name}</span>
                <span className="badge-green">{c.count} fragmentów</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* How it works */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Pipeline "Personal AI"</h2>
        <ol className="space-y-3">
          {[
            ["Auto-Sync →", "Podłącz konto GitHub → wszystkie Twoje repo zaindeksowane automatycznie co 24h"],
            ["Wiedza →", "Wgraj dokumenty, notatki, pliki — trafiają do RAG"],
            ["Chat →", "Każda rozmowa: BM25+vector search → kontekst z kodu → pamięć → odpowiedź"],
            ["Pamięć →", "Każda rozmowa zapamiętana — model zna Cię coraz lepiej z czasem"],
            ["Trening →", "Nowe commity → auto-dataset Q&A → LoRA fine-tuning (GPU)"],
          ].map(([step, desc], i) => (
            <li key={i} className="flex gap-3 text-sm">
              <span className="text-accent-400 font-bold w-28 shrink-0">{step}</span>
              <span className="text-gray-400">{desc}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="card flex items-center gap-4">
      <Icon size={22} className={color} />
      <div>
        <div className="text-xl font-bold text-gray-100">{value}</div>
        <div className="text-xs text-gray-500">{label}</div>
      </div>
    </div>
  );
}

function QuickLink({
  href,
  title,
  desc,
  label,
}: {
  href: string;
  title: string;
  desc: string;
  label: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="card hover:border-accent-500/50 transition-colors group block"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-semibold text-gray-200">{title}</span>
        <ExternalLink size={12} className="text-gray-500 group-hover:text-accent-400 transition-colors" />
      </div>
      <p className="text-xs text-gray-500 mb-3">{desc}</p>
      <span className="text-xs text-accent-400">{label} →</span>
    </a>
  );
}
