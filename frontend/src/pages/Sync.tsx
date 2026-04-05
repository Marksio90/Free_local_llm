import { useEffect, useState } from "react";
import { RefreshCw, Loader, Github, Calendar, CheckCircle, XCircle, Clock } from "lucide-react";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8080";

interface Repo {
  full_name: string;
  description: string;
  language: string;
  stars: number;
  updated_at: string;
  fork: boolean;
  private: boolean;
}

interface SyncStatus {
  running: boolean;
  last_run: string | null;
  repos_found: number;
  repos_synced: number;
  repos_failed: number;
  chunks_added: number;
  log: string[];
  error: string | null;
}

interface Schedule {
  enabled: boolean;
  next_run: string | null;
}

export default function Sync() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [loading, setLoading] = useState(false);
  const [includeForks, setIncludeForks] = useState(false);
  const [scheduleHours, setScheduleHours] = useState(24);
  const [hasToken, setHasToken] = useState<boolean | null>(null);

  const refresh = async () => {
    try {
      const [s, sc] = await Promise.all([
        fetch(`${BASE}/api/sync/status`).then((r) => r.json()),
        fetch(`${BASE}/api/sync/schedule`).then((r) => r.json()),
      ]);
      setStatus(s);
      setSchedule(sc);
    } catch {}
  };

  const loadRepos = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/api/sync/repos`).then((x) => x.json());
      if (r.error) {
        setHasToken(false);
      } else {
        setHasToken(true);
        setRepos(r.repos ?? []);
      }
    } catch {
      setHasToken(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    loadRepos();
    const t = setInterval(() => {
      if (status?.running) refresh();
    }, 3000);
    return () => clearInterval(t);
  }, []);

  const triggerSync = async () => {
    await fetch(`${BASE}/api/sync/trigger`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include_forks: includeForks, include_stars: false }),
    });
    setTimeout(refresh, 1000);
  };

  const setAutoSync = async (enabled: boolean) => {
    await fetch(`${BASE}/api/sync/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, interval_hours: scheduleHours }),
    });
    refresh();
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">GitHub Auto-Sync</h1>
        <p className="text-gray-500 text-sm mt-1">
          Podłącz swoje konto GitHub — model pozna WSZYSTKIE Twoje repozytoria
        </p>
      </div>

      {/* Token status */}
      {hasToken === false && (
        <div className="card border-yellow-500/30 bg-yellow-900/10">
          <div className="flex items-start gap-3">
            <XCircle size={16} className="text-yellow-400 mt-0.5 shrink-0" />
            <div>
              <div className="text-sm font-semibold text-yellow-300">Brak GITHUB_TOKEN</div>
              <p className="text-xs text-gray-400 mt-1">
                Dodaj token do pliku <code className="text-accent-300">.env</code>:
              </p>
              <div className="mt-2 bg-dark-800 rounded p-2 text-xs font-mono text-gray-300">
                GITHUB_TOKEN=ghp_TwojTokenTutaj
              </div>
              <p className="text-xs text-gray-500 mt-2">
                Generuj na: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens<br />
                Wymagane scope: <code>repo</code> (read)
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Sync controls */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Github size={14} />
          Uruchom sync
        </h2>
        <div className="flex items-center gap-4 mb-4">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={includeForks}
              onChange={(e) => setIncludeForks(e.target.checked)}
              className="rounded"
            />
            Uwzględnij forki
          </label>
        </div>
        <button
          onClick={triggerSync}
          disabled={status?.running || hasToken === false}
          className="btn-primary flex items-center gap-2"
        >
          {status?.running
            ? <><Loader size={14} className="animate-spin" />Sync w toku...</>
            : <><RefreshCw size={14} />Sync wszystkich repo</>
          }
        </button>
        <p className="text-xs text-gray-600 mt-2">
          Model pobierze i zaindeksuje cały Twój kod. Im więcej repo, tym dłużej.
        </p>
      </div>

      {/* Status */}
      {status && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Status</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-4">
            <StatBadge label="Repo znaleziono" value={status.repos_found} />
            <StatBadge label="Zsynced" value={status.repos_synced} color="text-green-400" />
            <StatBadge label="Błędów" value={status.repos_failed} color="text-red-400" />
            <StatBadge label="Fragmentów +" value={status.chunks_added} color="text-accent-400" />
          </div>
          {status.last_run && (
            <p className="text-xs text-gray-500 mb-3">
              Ostatni sync: {new Date(status.last_run).toLocaleString("pl")}
            </p>
          )}
          {status.error && (
            <div className="text-xs text-red-400 mb-3">{status.error}</div>
          )}
          {status.log.length > 0 && (
            <div className="bg-dark-800 rounded-lg p-3 max-h-48 overflow-y-auto">
              {status.log.slice(-30).map((line, i) => (
                <div key={i} className="text-xs font-mono text-gray-400">{line}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Auto-sync schedule */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Calendar size={14} className="text-blue-400" />
          Automatyczny sync
        </h2>
        <div className="flex items-center gap-3 mb-3">
          <span className="text-sm text-gray-400">Co</span>
          <input
            type="number"
            min={1}
            max={168}
            value={scheduleHours}
            onChange={(e) => setScheduleHours(Number(e.target.value))}
            className="input w-20"
          />
          <span className="text-sm text-gray-400">godzin</span>
        </div>
        <div className="flex gap-3">
          <button onClick={() => setAutoSync(true)} className="btn-primary flex items-center gap-2">
            <Calendar size={13} />
            Włącz auto-sync
          </button>
          <button onClick={() => setAutoSync(false)} className="btn-ghost">
            Wyłącz
          </button>
        </div>
        {schedule?.enabled && schedule.next_run && (
          <p className="text-xs text-green-400 mt-2 flex items-center gap-1">
            <Clock size={10} />
            Następny sync: {new Date(schedule.next_run).toLocaleString("pl")}
          </p>
        )}
      </div>

      {/* Repo list */}
      {repos.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">
            Twoje repozytoria ({repos.length})
          </h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {repos.map((r) => (
              <div key={r.full_name} className="flex items-center justify-between py-2 border-b border-dark-500 last:border-0">
                <div>
                  <span className="text-sm text-gray-200 font-mono">{r.full_name}</span>
                  {r.description && (
                    <p className="text-xs text-gray-500 mt-0.5 truncate max-w-xs">{r.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-3">
                  {r.language && <span className="badge-blue text-[10px]">{r.language}</span>}
                  {r.fork && <span className="badge-yellow text-[10px]">fork</span>}
                  {r.private && <span className="badge-red text-[10px]">private</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatBadge({ label, value, color = "text-gray-200" }: { label: string; value: number; color?: string }) {
  return (
    <div className="bg-dark-800 rounded-lg p-3">
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}
