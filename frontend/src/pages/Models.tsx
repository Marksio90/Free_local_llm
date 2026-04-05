import { useEffect, useState } from "react";
import { api, ModelInfo } from "../api/client";
import { Cpu, Download, Trash2, RefreshCw } from "lucide-react";

const RECOMMENDED = [
  { name: "qwen3:4b", desc: "Startowy – ogólny asystent (8-12 GB RAM)", tag: "Rekomendowany" },
  { name: "qwen2.5:7b", desc: "Mocniejszy dialog i analiza (16 GB RAM)", tag: "Zaawansowany" },
  { name: "qwen2.5-coder:7b", desc: "Specjalista od kodu (16 GB RAM)", tag: "Kodowanie" },
  { name: "nomic-embed-text", desc: "Embeddingi do RAG (wymagany dla bazy wiedzy)", tag: "Wymagany" },
  { name: "llama3.2:3b", desc: "Lekki – szybki na CPU (8 GB RAM)", tag: "CPU" },
];

export default function Models() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [pulling, setPulling] = useState<string | null>(null);
  const [pullLog, setPullLog] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    api.models.list()
      .then((r) => setModels(r.models ?? []))
      .catch(() => setModels([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { refresh(); }, []);

  const pull = async (name: string) => {
    setPulling(name);
    setPullLog("");
    try {
      const res = await api.models.pull(name);
      const reader = res.body?.getReader();
      if (!reader) return;
      const dec = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = dec.decode(value).split("\n").filter(Boolean);
        for (const line of lines) {
          try {
            const obj = JSON.parse(line);
            setPullLog(obj.status ?? line);
          } catch {
            setPullLog(line);
          }
        }
      }
      refresh();
    } catch (e) {
      setPullLog(`Błąd: ${e}`);
    } finally {
      setPulling(null);
    }
  };

  const del = async (name: string) => {
    if (!confirm(`Usunąć model ${name}?`)) return;
    await api.models.delete(name).catch(() => {});
    refresh();
  };

  const installed = new Set(models.map((m) => m.name));

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Modele</h1>
          <p className="text-gray-500 text-sm mt-1">Zarządzaj modelami Ollama</p>
        </div>
        <button onClick={refresh} className="btn-ghost flex items-center gap-2">
          <RefreshCw size={14} />
          Odśwież
        </button>
      </div>

      {/* Installed */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Cpu size={14} className="text-accent-400" />
          Zainstalowane ({models.length})
        </h2>
        {loading ? (
          <p className="text-gray-500 text-sm">Ładowanie...</p>
        ) : models.length === 0 ? (
          <p className="text-gray-500 text-sm">Brak modeli. Pobierz poniżej.</p>
        ) : (
          <div className="space-y-2">
            {models.map((m) => (
              <div key={m.name} className="flex items-center justify-between py-2 border-b border-dark-500 last:border-0">
                <div>
                  <span className="text-sm text-gray-200 font-mono">{m.name}</span>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {m.size ? `${(m.size / 1e9).toFixed(1)} GB` : ""}
                    {m.details?.parameter_size && ` · ${m.details.parameter_size}`}
                    {m.details?.quantization_level && ` · ${m.details.quantization_level}`}
                  </div>
                </div>
                <button onClick={() => del(m.name)} className="text-gray-600 hover:text-red-400 transition-colors">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pull progress */}
      {pulling && (
        <div className="card border-accent-500/30">
          <div className="text-xs text-accent-300 mb-1">Pobieranie: {pulling}</div>
          <div className="text-xs text-gray-400 font-mono bg-dark-800 rounded p-2">{pullLog || "..."}</div>
        </div>
      )}

      {/* Recommended */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Rekomendowane modele</h2>
        <div className="space-y-3">
          {RECOMMENDED.map((m) => (
            <div key={m.name} className="flex items-center justify-between py-2 border-b border-dark-500 last:border-0">
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm text-gray-200 font-mono">{m.name}</span>
                  <span className={
                    m.tag === "Wymagany" ? "badge-yellow" :
                    m.tag === "Rekomendowany" ? "badge-green" : "badge-blue"
                  }>{m.tag}</span>
                  {installed.has(m.name) && <span className="badge-green">✓ Zainstalowany</span>}
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{m.desc}</p>
              </div>
              <button
                onClick={() => pull(m.name)}
                disabled={!!pulling || installed.has(m.name)}
                className="btn-primary flex items-center gap-1.5 ml-4 shrink-0"
              >
                <Download size={13} />
                {installed.has(m.name) ? "OK" : "Pobierz"}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Custom pull */}
      <CustomPull onPull={pull} pulling={pulling} />
    </div>
  );
}

function CustomPull({ onPull, pulling }: { onPull: (n: string) => void; pulling: string | null }) {
  const [name, setName] = useState("");
  return (
    <div className="card">
      <h2 className="text-sm font-semibold text-gray-300 mb-4">Pobierz dowolny model</h2>
      <div className="flex gap-3">
        <input
          className="input"
          placeholder="np. mistral:7b, phi3:mini, gemma2:2b"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && name && onPull(name)}
        />
        <button
          onClick={() => name && onPull(name)}
          disabled={!name || !!pulling}
          className="btn-primary flex items-center gap-2 whitespace-nowrap"
        >
          <Download size={13} />
          Pobierz
        </button>
      </div>
      <p className="text-xs text-gray-600 mt-2">
        Przeglądaj modele:{" "}
        <a href="https://ollama.com/library" target="_blank" rel="noreferrer" className="text-accent-400 hover:underline">
          ollama.com/library
        </a>
      </p>
    </div>
  );
}
