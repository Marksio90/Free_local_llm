import { useEffect, useState } from "react";
import { Globe, Plus, Trash2, RefreshCw, Loader, Rss, Search, BookOpen, Zap } from "lucide-react";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8080";

interface Topic {
  name: string;
  source: string;
  enabled: boolean;
  crawl_interval_hours: number;
  last_crawled: string | null;
  crawl_count: number;
  added_at: string;
}

interface Feed {
  url: string;
  name: string;
  category: string;
}

interface Stats {
  topics_tracked: number;
  topics_crawled: number;
  web_intel_chunks: number;
  github_stars_chunks: number;
  github_gists_chunks: number;
  github_activity_chunks: number;
  feeds_subscribed: number;
}

export default function Intel() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [newTopic, setNewTopic] = useState("");
  const [newFeedUrl, setNewFeedUrl] = useState("");
  const [newFeedName, setNewFeedName] = useState("");
  const [crawlingAll, setCrawlingAll] = useState(false);
  const [crawlingTopic, setCrawlingTopic] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [ingestingUrl, setIngestingUrl] = useState(false);
  const [urlResult, setUrlResult] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [t, f, s] = await Promise.all([
        fetch(`${BASE}/api/intel/topics`).then((r) => r.json()),
        fetch(`${BASE}/api/intel/feeds`).then((r) => r.json()),
        fetch(`${BASE}/api/intel/stats`).then((r) => r.json()),
      ]);
      setTopics(t);
      setFeeds(f);
      setStats(s);
    } catch {}
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, []);

  const addTopic = async () => {
    if (!newTopic.trim()) return;
    await fetch(`${BASE}/api/intel/topics`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newTopic.trim(), crawl_hours: 24 }),
    });
    setNewTopic("");
    refresh();
  };

  const deleteTopic = async (name: string) => {
    await fetch(`${BASE}/api/intel/topics/${encodeURIComponent(name)}`, { method: "DELETE" });
    refresh();
  };

  const crawlTopic = async (name: string) => {
    setCrawlingTopic(name);
    await fetch(`${BASE}/api/intel/topics/${encodeURIComponent(name)}/crawl`, { method: "POST" });
    setTimeout(() => { setCrawlingTopic(null); refresh(); }, 2000);
  };

  const crawlAll = async () => {
    setCrawlingAll(true);
    await fetch(`${BASE}/api/intel/crawl-all`, { method: "POST" });
    setTimeout(() => { setCrawlingAll(false); refresh(); }, 3000);
  };

  const addFeed = async () => {
    if (!newFeedUrl.trim()) return;
    await fetch(`${BASE}/api/intel/feeds`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: newFeedUrl.trim(), name: newFeedName.trim() }),
    });
    setNewFeedUrl("");
    setNewFeedName("");
    refresh();
  };

  const ingestUrl = async () => {
    if (!urlInput.trim()) return;
    setIngestingUrl(true);
    setUrlResult(null);
    try {
      const r = await fetch(`${BASE}/api/intel/ingest-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: urlInput.trim() }),
      }).then((x) => x.json());
      setUrlResult(`${r.status === "ok" ? "✓" : "✗"} ${r.url} → ${r.chunks || 0} fragmentów`);
      setUrlInput("");
    } catch (e) {
      setUrlResult(`Błąd: ${e}`);
    } finally {
      setIngestingUrl(false);
    }
  };

  const totalKnowledge = stats
    ? stats.web_intel_chunks + stats.github_stars_chunks + stats.github_gists_chunks + stats.github_activity_chunks
    : 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100 flex items-center gap-2">
          <Globe size={22} className="text-accent-400" />
          Web Intelligence
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Model automatycznie zbiera wiedzę o Twoich tematach z internetu — za darmo, bez API
        </p>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatBox label="Tematy śledzone" value={stats.topics_tracked} color="text-accent-400" />
          <StatBox label="Tematy crawlowane" value={stats.topics_crawled} color="text-green-400" />
          <StatBox label="Fragmentów web" value={stats.web_intel_chunks} color="text-blue-400" />
          <StatBox label="Łącznie (wszystkie źródła)" value={totalKnowledge} color="text-purple-400" />
        </div>
      )}

      {/* How it works */}
      <div className="card border-accent-500/20 bg-accent-500/5">
        <div className="text-xs font-semibold text-accent-300 mb-2 flex items-center gap-2">
          <Zap size={12} />
          Jak to działa (automatycznie)
        </div>
        <div className="grid gap-1.5 text-xs text-gray-400">
          {[
            "Pytasz w chacie → system wyciąga tematy → DuckDuckGo top strony → ChromaDB",
            "GitHub Sync → Stars READMEs + Gists + Issue comments → baza wiedzy",
            "RSS feeds → nowe artykuły co 12h → automatyczna ingestia",
            "Scheduler co 12h → odświeża wszystkie tematy → model zawsze aktualny",
          ].map((s, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-accent-500 shrink-0">{i + 1}.</span>
              <span>{s}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Crawl all */}
      <div className="flex gap-3">
        <button onClick={crawlAll} disabled={crawlingAll} className="btn-primary flex items-center gap-2">
          {crawlingAll ? <Loader size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Crawl wszystkich tematów teraz
        </button>
        <button onClick={refresh} className="btn-ghost flex items-center gap-2">
          <RefreshCw size={13} />
          Odśwież
        </button>
      </div>

      {/* Topics */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Search size={14} className="text-accent-400" />
          Śledzone tematy ({topics.length})
        </h2>

        {/* Add topic */}
        <div className="flex gap-3 mb-4">
          <input
            className="input"
            placeholder='np. "docker networking", "qwen fine-tuning", "FastAPI performance"'
            value={newTopic}
            onChange={(e) => setNewTopic(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addTopic()}
          />
          <button onClick={addTopic} disabled={!newTopic.trim()} className="btn-primary whitespace-nowrap flex items-center gap-1.5">
            <Plus size={13} />
            Dodaj
          </button>
        </div>

        <div className="space-y-1.5 max-h-80 overflow-y-auto">
          {topics.map((t) => (
            <div key={t.name} className="flex items-center justify-between py-1.5 px-3 bg-dark-800 rounded-lg">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm text-gray-200 truncate">{t.name}</span>
                <SourceBadge source={t.source} />
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-2">
                {t.last_crawled ? (
                  <span className="text-[10px] text-gray-600">
                    {new Date(t.last_crawled).toLocaleDateString("pl")} ({t.crawl_count}×)
                  </span>
                ) : (
                  <span className="text-[10px] text-yellow-600">nie crawlowany</span>
                )}
                <button
                  onClick={() => crawlTopic(t.name)}
                  disabled={crawlingTopic === t.name}
                  className="text-gray-600 hover:text-accent-400 transition-colors"
                  title="Crawl teraz"
                >
                  {crawlingTopic === t.name ? <Loader size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                </button>
                <button onClick={() => deleteTopic(t.name)} className="text-gray-600 hover:text-red-400 transition-colors">
                  <Trash2 size={11} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Direct URL ingest */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Globe size={14} className="text-blue-400" />
          Wgraj konkretną stronę
        </h2>
        <div className="flex gap-3">
          <input
            className="input"
            placeholder="https://docs.example.com/page"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ingestUrl()}
          />
          <button onClick={ingestUrl} disabled={!urlInput.trim() || ingestingUrl} className="btn-primary whitespace-nowrap flex items-center gap-1.5">
            {ingestingUrl ? <Loader size={13} className="animate-spin" /> : <BookOpen size={13} />}
            Wgraj
          </button>
        </div>
        {urlResult && (
          <p className={`text-xs mt-2 font-mono ${urlResult.startsWith("✓") ? "text-green-400" : "text-red-400"}`}>
            {urlResult}
          </p>
        )}
        <p className="text-xs text-gray-600 mt-2">
          Dokumentacja, artykuły, tutoriale — trafilatura wyciągnie czysty tekst
        </p>
      </div>

      {/* RSS Feeds */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Rss size={14} className="text-orange-400" />
          RSS Feeds ({feeds.length})
        </h2>
        <div className="flex gap-2 mb-4">
          <input className="input" placeholder="https://example.com/rss.xml" value={newFeedUrl} onChange={(e) => setNewFeedUrl(e.target.value)} />
          <input className="input w-40" placeholder="Nazwa" value={newFeedName} onChange={(e) => setNewFeedName(e.target.value)} />
          <button onClick={addFeed} disabled={!newFeedUrl.trim()} className="btn-primary whitespace-nowrap flex items-center gap-1.5">
            <Plus size={13} />
            Dodaj
          </button>
        </div>
        <div className="space-y-1.5">
          {feeds.map((f) => (
            <div key={f.url} className="flex items-center justify-between py-1.5 px-3 bg-dark-800 rounded-lg">
              <div>
                <span className="text-sm text-gray-200">{f.name}</span>
                <span className="text-xs text-gray-600 ml-2 truncate max-w-xs block">{f.url}</span>
              </div>
              <span className="badge-blue text-[10px]">{f.category}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatBox({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="card">
      <div className={`text-xl font-bold ${color}`}>{value.toLocaleString()}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const map: Record<string, string> = {
    manual: "badge-blue",
    chat_auto: "badge-green",
    github_star: "badge-yellow",
    github_language: "badge-blue",
    repo_description: "badge-blue",
  };
  const labels: Record<string, string> = {
    manual: "ręczny",
    chat_auto: "z chatu",
    github_star: "GitHub ★",
    github_language: "GitHub",
    repo_description: "repo",
  };
  const cls = map[source] || "badge-blue";
  return <span className={`${cls} text-[9px]`}>{labels[source] || source}</span>;
}
