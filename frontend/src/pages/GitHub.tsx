import { useEffect, useState } from "react";
import { api, IngestJob } from "../api/client";
import { Github, Search, RefreshCw, Loader } from "lucide-react";

export default function GitHub() {
  const [repoUrl, setRepoUrl] = useState("");
  const [collectionName, setCollectionName] = useState("");
  const [jobs, setJobs] = useState<(IngestJob & { job_id?: string; collection?: string })[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [query, setQuery] = useState("");
  const [searchCollection, setSearchCollection] = useState("");
  const [searchResults, setSearchResults] = useState<{ content: string; score: number; metadata: Record<string, unknown> }[]>([]);
  const [searching, setSearching] = useState(false);

  const refreshJobs = () => {
    api.github.jobs().then(setJobs).catch(() => {});
  };

  useEffect(() => {
    refreshJobs();
    const t = setInterval(refreshJobs, 3000);
    return () => clearInterval(t);
  }, []);

  const ingest = async () => {
    if (!repoUrl.startsWith("https://github.com/")) {
      alert("Podaj pełny URL repozytorium GitHub (https://github.com/...)");
      return;
    }
    setSubmitting(true);
    try {
      await api.github.ingest(repoUrl, collectionName || undefined);
      setRepoUrl("");
      setCollectionName("");
      refreshJobs();
    } catch (e) {
      alert(`Błąd: ${e}`);
    } finally {
      setSubmitting(false);
    }
  };

  const search = async () => {
    if (!query || !searchCollection) return;
    setSearching(true);
    try {
      const r = await api.github.search(query, searchCollection);
      setSearchResults(r.results);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">GitHub</h1>
        <p className="text-gray-500 text-sm mt-1">
          Wgraj repozytoria GitHub do bazy wektorowej – model zyska ich kontekst
        </p>
      </div>

      {/* Ingest form */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Github size={14} className="text-gray-400" />
          Zaingestionuj repozytorium
        </h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">URL repozytorium *</label>
            <input
              className="input"
              placeholder="https://github.com/owner/repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">
              Nazwa kolekcji (opcjonalna – domyślnie generowana z URL)
            </label>
            <input
              className="input"
              placeholder="np. moje_repo"
              value={collectionName}
              onChange={(e) => setCollectionName(e.target.value)}
            />
          </div>
          <button
            onClick={ingest}
            disabled={submitting || !repoUrl}
            className="btn-primary flex items-center gap-2"
          >
            {submitting ? <Loader size={14} className="animate-spin" /> : <Github size={14} />}
            {submitting ? "Kolejkuję..." : "Zaingestionuj"}
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-3">
          Repo zostanie sklonowane lokalnie, podzielone na fragmenty i zaindeksowane w ChromaDB.
          Prywatne repo wymaga tokenu GitHub w .env (GITHUB_TOKEN).
        </p>
      </div>

      {/* Jobs */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-300">Zadania ingestii</h2>
          <button onClick={refreshJobs} className="text-gray-500 hover:text-gray-300 transition-colors">
            <RefreshCw size={13} />
          </button>
        </div>
        {jobs.length === 0 ? (
          <p className="text-gray-500 text-sm">Brak zadań.</p>
        ) : (
          <div className="space-y-2">
            {[...jobs].reverse().map((job, i) => (
              <div key={i} className="flex items-start justify-between py-2 border-b border-dark-500 last:border-0">
                <div>
                  <div className="text-sm text-gray-200 font-mono">{job.repo ?? "—"}</div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    Kolekcja: {job.collection ?? "—"} ·{" "}
                    {job.ingested != null ? `${job.ingested} fragmentów` : ""}
                    {job.total_files != null ? ` z ${job.total_files} plików` : ""}
                    {job.error && <span className="text-red-400"> · {job.error}</span>}
                  </div>
                </div>
                <JobBadge status={job.status} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Search */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Search size={14} className="text-blue-400" />
          Wyszukiwanie semantyczne w repo
        </h2>
        <div className="space-y-3">
          <div className="flex gap-3">
            <input
              className="input"
              placeholder="Nazwa kolekcji (np. owner__repo)"
              value={searchCollection}
              onChange={(e) => setSearchCollection(e.target.value)}
            />
            <input
              className="input"
              placeholder="Zapytanie (np. authentication middleware)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
            />
            <button onClick={search} disabled={!query || !searchCollection || searching} className="btn-primary whitespace-nowrap flex items-center gap-1.5">
              {searching ? <Loader size={13} className="animate-spin" /> : <Search size={13} />}
              Szukaj
            </button>
          </div>
        </div>
        {searchResults.length > 0 && (
          <div className="mt-4 space-y-3">
            {searchResults.map((r, i) => (
              <div key={i} className="bg-dark-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 font-mono">
                    {String(r.metadata?.path ?? "")}
                  </span>
                  <span className="badge-green">score: {r.score}</span>
                </div>
                <pre className="text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap">{r.content.slice(0, 500)}</pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function JobBadge({ status }: { status: string }) {
  if (status === "done") return <span className="badge-green">Gotowe</span>;
  if (status === "running") return <span className="badge-yellow"><Loader size={10} className="animate-spin" />W toku</span>;
  if (status === "error") return <span className="badge-red">Błąd</span>;
  return <span className="badge-blue">{status}</span>;
}
