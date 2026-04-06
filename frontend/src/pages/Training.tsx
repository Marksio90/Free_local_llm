import { useEffect, useState } from "react";
import { api, DatasetInfo, TrainingJob, FineTuneInstructions, LearnStatus } from "../api/client";
import { Zap, Database, RefreshCw, Loader, Terminal, Info, Brain, BookOpen } from "lucide-react";

export default function Training() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [jobs, setJobs] = useState<(TrainingJob & { job_id?: string })[]>([]);
  const [instructions, setInstructions] = useState<FineTuneInstructions | null>(null);
  const [learnStatus, setLearnStatus] = useState<LearnStatus | null>(null);
  const [collection, setCollection] = useState("");
  const [outputName, setOutputName] = useState("dataset");
  const [maxSamples, setMaxSamples] = useState(500);
  const [model, setModel] = useState("");
  const [building, setBuilding] = useState(false);
  const [triggeringLearn, setTriggeringLearn] = useState(false);

  const refresh = () => {
    api.training.datasets().then(setDatasets).catch(() => {});
    api.training.jobs().then(setJobs).catch(() => {});
    api.training.learnStatus().then(setLearnStatus).catch(() => {});
  };

  useEffect(() => {
    refresh();
    api.training.instructions().then(setInstructions).catch(() => {});
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  const triggerLearn = async () => {
    setTriggeringLearn(true);
    try {
      const r = await api.training.triggerLearn();
      if (r.status === "no_new_repos") {
        alert("Brak nowych repo do uczenia. Najpierw uruchom GitHub Auto-Sync.");
      }
    } catch (e) {
      alert(`Błąd: ${e}`);
    } finally {
      setTriggeringLearn(false);
      refresh();
    }
  };

  const buildDataset = async () => {
    if (!collection) return;
    setBuilding(true);
    try {
      await api.training.buildDataset(collection, outputName, maxSamples, model);
      refresh();
    } catch (e) {
      alert(`Błąd: ${e}`);
    } finally {
      setBuilding(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Trening</h1>
        <p className="text-gray-500 text-sm mt-1">
          Buduj datasety i uruchamiaj fine-tuning LoRA na własnych danych
        </p>
      </div>

      {/* Workflow info */}
      <div className="card border-accent-500/20">
        <h2 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <Info size={14} className="text-accent-400" />
          Jak działa fine-tuning
        </h2>
        <ol className="space-y-2 text-sm">
          {[
            ["1. Ingestia", "GitHub → repozytorium trafia do ChromaDB jako wektory"],
            ["2. Dataset", "Model generuje pary pytanie–odpowiedź z fragmentów kodu → plik JSONL"],
            ["3. LoRA", "Lekkie dostrajanie modelu na datasecie (wymaga GPU, kontener trainer)"],
            ["4. Export", "Model eksportowany do GGUF → rejestracja w Ollama → gotowy do użycia"],
          ].map(([step, desc]) => (
            <li key={step} className="flex gap-3">
              <span className="text-accent-400 font-mono text-xs w-20 shrink-0 pt-0.5">{step}</span>
              <span className="text-gray-400 text-xs">{desc}</span>
            </li>
          ))}
        </ol>
        <div className="mt-3 p-2 bg-yellow-900/20 rounded text-xs text-yellow-400 border border-yellow-800/40">
          Bez GPU: używaj RAG (baza wektorowa) – model automatycznie dostaje kontekst z Twoich dokumentów bez treningu.
        </div>
      </div>

      {/* Build dataset */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Database size={14} className="text-blue-400" />
          Buduj dataset (JSONL)
        </h2>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Kolekcja źródłowa *</label>
            <input className="input" placeholder="np. owner__repo" value={collection} onChange={(e) => setCollection(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Nazwa wyjściowa</label>
            <input className="input" placeholder="dataset" value={outputName} onChange={(e) => setOutputName(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Maks. przykładów</label>
            <input className="input" type="number" value={maxSamples} onChange={(e) => setMaxSamples(Number(e.target.value))} min={10} max={10000} />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Model (domyślny z .env)</label>
            <input className="input" placeholder="qwen3:4b" value={model} onChange={(e) => setModel(e.target.value)} />
          </div>
        </div>
        <button onClick={buildDataset} disabled={!collection || building} className="btn-primary flex items-center gap-2">
          {building ? <Loader size={14} className="animate-spin" /> : <Database size={14} />}
          {building ? "Generuję dataset..." : "Generuj dataset"}
        </button>
        <p className="text-xs text-gray-600 mt-2">
          Model LLM generuje pary Q&amp;A ze fragmentów kodu. Im więcej przykładów, tym dłużej trwa.
        </p>
      </div>

      {/* Jobs */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-300">Zadania generowania ({jobs.length})</h2>
          <button onClick={refresh} className="text-gray-500 hover:text-gray-300"><RefreshCw size={13} /></button>
        </div>
        {jobs.length === 0 ? (
          <p className="text-gray-500 text-sm">Brak zadań.</p>
        ) : (
          <div className="space-y-2">
            {[...jobs].reverse().map((job, i) => (
              <div key={i} className="py-2 border-b border-dark-500 last:border-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">{job.step ?? job.file ?? "—"}</span>
                  <JobBadge status={job.status} />
                </div>
                {job.pairs_generated != null && (
                  <div className="text-xs text-green-400 mt-1">{job.pairs_generated} par Q&A wygenerowanych</div>
                )}
                {job.error && <div className="text-xs text-red-400 mt-1">{job.error}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Datasets */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Database size={14} className="text-green-400" />
          Gotowe datasety
        </h2>
        {datasets.length === 0 ? (
          <p className="text-gray-500 text-sm">Brak plików JSONL. Wygeneruj dataset powyżej.</p>
        ) : (
          <div className="space-y-2">
            {datasets.map((d) => (
              <div key={d.name} className="flex items-center justify-between py-2 border-b border-dark-500 last:border-0">
                <div>
                  <span className="text-sm font-mono text-gray-200">{d.name}</span>
                  <div className="text-xs text-gray-500">{d.samples} przykładów · {d.size_kb} KB</div>
                </div>
                <span className="badge-green">JSONL</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Learn status */}
      {learnStatus && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
              <Brain size={14} className="text-pink-400" />
              Status automatycznego uczenia
            </h2>
            <button
              onClick={triggerLearn}
              disabled={triggeringLearn || learnStatus.running}
              className="btn-primary flex items-center gap-2 text-xs py-1 px-3"
            >
              {triggeringLearn || learnStatus.running
                ? <><Loader size={12} className="animate-spin" />Uczę się...</>
                : <><Zap size={12} />Uruchom uczenie</>}
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-4">
            <div className="bg-dark-800 rounded-lg p-3">
              <div className="text-xl font-bold text-green-400">{learnStatus.learned_repos.length}</div>
              <div className="text-xs text-gray-500">Repo wyuczone</div>
            </div>
            <div className="bg-dark-800 rounded-lg p-3">
              <div className="text-xl font-bold text-yellow-400">{learnStatus.pending_repos.length}</div>
              <div className="text-xs text-gray-500">Oczekuje</div>
            </div>
            <div className="bg-dark-800 rounded-lg p-3">
              <div className="text-xl font-bold text-accent-400">{learnStatus.total_samples}</div>
              <div className="text-xs text-gray-500">Par Q&amp;A</div>
            </div>
            <div className="bg-dark-800 rounded-lg p-3">
              <div className="text-xl font-bold text-blue-400">{learnStatus.wiki_topics_learned.length}</div>
              <div className="text-xs text-gray-500">Tematy Wiki</div>
            </div>
          </div>
          {learnStatus.last_learn && (
            <p className="text-xs text-gray-500 mb-3">
              Ostatnie uczenie: {new Date(learnStatus.last_learn).toLocaleString("pl")}
            </p>
          )}
          {learnStatus.last_dataset && (
            <p className="text-xs text-gray-500 mb-3">
              Ostatni dataset: <span className="font-mono text-gray-400">{learnStatus.last_dataset}</span>
            </p>
          )}
          {learnStatus.gpu_training_done && (
            <div className="mb-3 p-2 bg-green-900/20 rounded text-xs text-green-400 border border-green-800/40">
              LoRA fine-tuning ukończony — model eksportowany do GGUF
            </div>
          )}
          {learnStatus.log.length > 0 && (
            <div className="bg-dark-800 rounded-lg p-3 max-h-40 overflow-y-auto">
              {learnStatus.log.slice(-20).map((line, i) => (
                <div key={i} className="text-xs font-mono text-gray-400">{line}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* LoRA instructions */}
      {instructions && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <Terminal size={14} className="text-yellow-400" />
            Uruchomienie fine-tuningu LoRA (GPU)
          </h2>
          <p className="text-xs text-gray-400 mb-3">{instructions.info}</p>
          <div className="bg-dark-800 rounded-lg p-4 space-y-1.5">
            {instructions.steps.map((step, i) => (
              <div key={i} className="text-xs font-mono text-gray-300">{step}</div>
            ))}
          </div>
          <div className="mt-3 p-2 bg-blue-900/20 rounded text-xs text-blue-300 border border-blue-800/30">
            {instructions.without_gpu}
          </div>
        </div>
      )}
    </div>
  );
}

function JobBadge({ status }: { status: string }) {
  if (status === "done") return <span className="badge-green">Gotowe</span>;
  if (status === "running") return <span className="badge-yellow inline-flex items-center gap-1"><Loader size={10} className="animate-spin" />W toku</span>;
  if (status === "error") return <span className="badge-red">Błąd</span>;
  return <span className="badge-blue">{status}</span>;
}
