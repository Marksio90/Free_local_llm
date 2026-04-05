import { useEffect, useState } from "react";
import { Brain, Search, Plus, User, RefreshCw, Loader } from "lucide-react";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8080";

interface MemoryItem {
  content: string;
  metadata: { type?: string; category?: string; timestamp?: string; session_id?: string };
  score?: number;
}

interface Profile {
  name?: string;
  github_login?: string;
  languages?: string[];
  bio?: string;
  total_repos?: number;
  last_updated?: string;
}

export default function Memory() {
  const [stats, setStats] = useState<{ total_memories: number; profile_set: boolean } | null>(null);
  const [profile, setProfile] = useState<Profile>({});
  const [editProfile, setEditProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({ name: "", languages: "", style: "", bio: "" });
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemoryItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [fact, setFact] = useState("");
  const [addingFact, setAddingFact] = useState(false);

  const refresh = async () => {
    try {
      const [s, p] = await Promise.all([
        fetch(`${BASE}/api/memory/stats`).then((r) => r.json()),
        fetch(`${BASE}/api/memory/profile`).then((r) => r.json()),
      ]);
      setStats(s);
      setProfile(p);
      setProfileForm({
        name: p.name || "",
        languages: (p.languages || []).join(", "),
        style: p.style || "",
        bio: p.bio || "",
      });
    } catch {}
  };

  useEffect(() => { refresh(); }, []);

  const search = async () => {
    if (!query) return;
    setSearching(true);
    try {
      const r = await fetch(`${BASE}/api/memory/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, n: 10 }),
      }).then((x) => x.json());
      setResults(r.results ?? []);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const addFact = async () => {
    if (!fact.trim()) return;
    setAddingFact(true);
    try {
      await fetch(`${BASE}/api/memory/facts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fact, category: "manual" }),
      });
      setFact("");
      refresh();
    } finally {
      setAddingFact(false);
    }
  };

  const saveProfile = async () => {
    await fetch(`${BASE}/api/memory/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: profileForm.name || undefined,
        languages: profileForm.languages ? profileForm.languages.split(",").map((s) => s.trim()) : undefined,
        style: profileForm.style || undefined,
        bio: profileForm.bio || undefined,
      }),
    });
    setEditProfile(false);
    refresh();
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Pamięć</h1>
          <p className="text-gray-500 text-sm mt-1">
            Co model wie o Tobie — rośnie z każdą rozmową
          </p>
        </div>
        <button onClick={refresh} className="text-gray-500 hover:text-gray-300">
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-4">
          <div className="card flex items-center gap-4">
            <Brain size={22} className="text-purple-400" />
            <div>
              <div className="text-xl font-bold text-gray-100">{stats.total_memories}</div>
              <div className="text-xs text-gray-500">Wspomnień</div>
            </div>
          </div>
          <div className="card flex items-center gap-4">
            <User size={22} className="text-accent-400" />
            <div>
              <div className="text-xl font-bold text-gray-100">{stats.profile_set ? "Tak" : "Nie"}</div>
              <div className="text-xs text-gray-500">Profil skonfigurowany</div>
            </div>
          </div>
        </div>
      )}

      {/* Profile */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
            <User size={14} className="text-accent-400" />
            Profil użytkownika
          </h2>
          <button onClick={() => setEditProfile(!editProfile)} className="text-xs text-accent-400 hover:text-accent-300">
            {editProfile ? "Anuluj" : "Edytuj"}
          </button>
        </div>

        {editProfile ? (
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Imię / nick</label>
              <input className="input" value={profileForm.name} onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })} placeholder="Jan Kowalski" />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Języki programowania (oddzielone przecinkami)</label>
              <input className="input" value={profileForm.languages} onChange={(e) => setProfileForm({ ...profileForm, languages: e.target.value })} placeholder="Python, TypeScript, Go" />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Styl pracy</label>
              <input className="input" value={profileForm.style} onChange={(e) => setProfileForm({ ...profileForm, style: e.target.value })} placeholder="np. krótkie odpowiedzi, komentarze po polsku" />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Bio / kontekst</label>
              <textarea className="input resize-none h-20" value={profileForm.bio} onChange={(e) => setProfileForm({ ...profileForm, bio: e.target.value })} placeholder="Czym się zajmujesz, co budujesz..." />
            </div>
            <button onClick={saveProfile} className="btn-primary">Zapisz profil</button>
          </div>
        ) : (
          <div className="space-y-2 text-sm">
            {profile.name && <div><span className="text-gray-500">Imię: </span><span className="text-gray-200">{profile.name}</span></div>}
            {profile.github_login && <div><span className="text-gray-500">GitHub: </span><span className="text-gray-200">{profile.github_login}</span></div>}
            {profile.languages?.length ? (
              <div>
                <span className="text-gray-500">Języki: </span>
                {profile.languages.map((l) => <span key={l} className="badge-blue mr-1">{l}</span>)}
              </div>
            ) : null}
            {profile.total_repos && <div><span className="text-gray-500">Repo: </span><span className="text-gray-200">{profile.total_repos}</span></div>}
            {profile.bio && <div><span className="text-gray-500">Bio: </span><span className="text-gray-200">{profile.bio}</span></div>}
            {!profile.name && !profile.languages?.length && (
              <p className="text-gray-600 text-xs">Profil pusty. Edytuj ręcznie lub uruchom GitHub Sync.</p>
            )}
          </div>
        )}
      </div>

      {/* Add fact */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Plus size={14} className="text-green-400" />
          Dodaj fakt o sobie
        </h2>
        <p className="text-xs text-gray-500 mb-3">
          Wszystko co chcesz żeby model o Tobie wiedział — preferencje, kontekst pracy, styl.
        </p>
        <div className="flex gap-3">
          <input
            className="input"
            placeholder='np. "Wolę zwięzłe odpowiedzi bez wstępów" albo "Piszę głównie backendy w FastAPI"'
            value={fact}
            onChange={(e) => setFact(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addFact()}
          />
          <button onClick={addFact} disabled={!fact.trim() || addingFact} className="btn-primary whitespace-nowrap flex items-center gap-1.5">
            {addingFact ? <Loader size={12} className="animate-spin" /> : <Plus size={13} />}
            Dodaj
          </button>
        </div>
      </div>

      {/* Search memory */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Search size={14} className="text-accent-400" />
          Przeszukaj pamięć
        </h2>
        <div className="flex gap-3 mb-4">
          <input
            className="input"
            placeholder="Co pamiętasz o...?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
          />
          <button onClick={search} disabled={!query || searching} className="btn-primary whitespace-nowrap flex items-center gap-1.5">
            {searching ? <Loader size={13} className="animate-spin" /> : <Search size={13} />}
            Szukaj
          </button>
        </div>
        {results.length > 0 && (
          <div className="space-y-2">
            {results.map((r, i) => (
              <div key={i} className="bg-dark-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="badge-blue text-[10px]">{r.metadata?.type || "memory"}</span>
                  {r.score && <span className="badge-green text-[10px]">score: {r.score}</span>}
                </div>
                <p className="text-xs text-gray-300 whitespace-pre-wrap">{r.content.slice(0, 400)}</p>
                {r.metadata?.timestamp && (
                  <p className="text-[10px] text-gray-600 mt-1">
                    {new Date(r.metadata.timestamp).toLocaleString("pl")}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
        {results.length === 0 && query && !searching && (
          <p className="text-gray-500 text-sm">Brak wyników. Zacznij rozmawiać — pamięć rośnie z każdą sesją.</p>
        )}
      </div>
    </div>
  );
}
