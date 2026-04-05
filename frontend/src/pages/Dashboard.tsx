import { useEffect, useState } from "react";
import { api, CollectionInfo, ModelInfo } from "../api/client";
import { Cpu, BookOpen, Github, Zap, ExternalLink, CheckCircle, XCircle } from "lucide-react";

export default function Dashboard() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  useEffect(() => {
    api.health().then(() => setBackendOk(true)).catch(() => setBackendOk(false));
    api.models.list().then((r) => setModels(r.models ?? [])).catch(() => {});
    api.knowledge.collections().then(setCollections).catch(() => {});
  }, []);

  const totalChunks = collections.reduce((s, c) => s + c.count, 0);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">Lokalne centrum AI – status systemu</p>
      </div>

      {/* Status */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Backend"
          value={backendOk === null ? "..." : backendOk ? "Online" : "Offline"}
          icon={backendOk ? CheckCircle : XCircle}
          color={backendOk ? "text-green-400" : "text-red-400"}
        />
        <StatCard label="Modele" value={models.length} icon={Cpu} color="text-accent-400" />
        <StatCard label="Kolekcje wiedzy" value={collections.length} icon={BookOpen} color="text-blue-400" />
        <StatCard label="Fragmentów w bazie" value={totalChunks} icon={Github} color="text-purple-400" />
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
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Jak to działa</h2>
        <ol className="space-y-3">
          {[
            ["GitHub →", "Zaingestionuj repo: kod trafia do ChromaDB jako wektory semantyczne"],
            ["Wiedza →", "Wgraj własne dokumenty: notatki, PDFy, pliki tekstowe"],
            ["Trening →", "Zbuduj dataset Q&A i uruchom fine-tuning LoRA (wymaga GPU)"],
            ["Czat →", "Model odpowiada z kontekstem Twojej wiedzy (RAG)"],
          ].map(([step, desc], i) => (
            <li key={i} className="flex gap-3 text-sm">
              <span className="text-accent-400 font-bold w-24 shrink-0">{step}</span>
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
