import { useEffect, useState, useRef } from "react";
import { api, CollectionInfo, SearchResult } from "../api/client";
import { BookOpen, Search, Trash2, Upload, Plus, RefreshCw } from "lucide-react";

export default function Knowledge() {
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [query, setQuery] = useState("");
  const [selectedCol, setSelectedCol] = useState("documents");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [adding, setAdding] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refreshCollections = () => {
    api.knowledge.collections().then(setCollections).catch(() => {});
  };

  useEffect(() => { refreshCollections(); }, []);

  const search = async () => {
    if (!query) return;
    setSearching(true);
    try {
      const r = await api.knowledge.search(query, selectedCol);
      setResults(r.results);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const addText = async () => {
    if (!text) return;
    setAdding(true);
    try {
      await api.knowledge.addText(text, source || "manual", selectedCol);
      setText("");
      setSource("");
      refreshCollections();
    } catch (e) {
      alert(`Błąd: ${e}`);
    } finally {
      setAdding(false);
    }
  };

  const upload = async (file: File) => {
    try {
      await api.knowledge.upload(file, selectedCol);
      refreshCollections();
    } catch (e) {
      alert(`Błąd wgrywania: ${e}`);
    }
  };

  const deleteCol = async (name: string) => {
    if (!confirm(`Usunąć kolekcję "${name}"? Tej operacji nie można cofnąć.`)) return;
    await api.knowledge.deleteCollection(name);
    refreshCollections();
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Wiedza</h1>
        <p className="text-gray-500 text-sm mt-1">Zarządzaj lokalną bazą wiedzy – dokumenty, notatki, pliki</p>
      </div>

      {/* Collections */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
            <BookOpen size={14} className="text-blue-400" />
            Kolekcje ({collections.length})
          </h2>
          <button onClick={refreshCollections} className="text-gray-500 hover:text-gray-300">
            <RefreshCw size={13} />
          </button>
        </div>
        {collections.length === 0 ? (
          <p className="text-gray-500 text-sm">Brak kolekcji. Dodaj tekst lub wgraj dokument poniżej.</p>
        ) : (
          <div className="space-y-2">
            {collections.map((c) => (
              <div key={c.name} className="flex items-center justify-between py-2 border-b border-dark-500 last:border-0">
                <div>
                  <span className="text-sm font-mono text-gray-200">{c.name}</span>
                  <span className="ml-2 badge-blue">{c.count} fragmentów</span>
                </div>
                <button onClick={() => deleteCol(c.name)} className="text-gray-600 hover:text-red-400 transition-colors">
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Kolekcja aktywna */}
      <div className="card">
        <label className="text-xs text-gray-500 mb-1 block">Aktywna kolekcja</label>
        <div className="flex gap-3">
          <input
            className="input"
            value={selectedCol}
            onChange={(e) => setSelectedCol(e.target.value)}
            placeholder="documents"
          />
        </div>
        <p className="text-xs text-gray-600 mt-1">Wszystkie operacje poniżej działają na tej kolekcji.</p>
      </div>

      {/* Add text */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Plus size={14} className="text-green-400" />
          Dodaj tekst
        </h2>
        <div className="space-y-3">
          <input className="input" placeholder="Źródło (np. moje-notatki.md)" value={source} onChange={(e) => setSource(e.target.value)} />
          <textarea
            className="input resize-none h-28"
            placeholder="Wklej tutaj tekst, notatkę, fragment dokumentacji..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button onClick={addText} disabled={!text || adding} className="btn-primary flex items-center gap-2">
            <Plus size={13} />
            {adding ? "Dodaję..." : "Dodaj do bazy"}
          </button>
        </div>
      </div>

      {/* Upload */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Upload size={14} className="text-purple-400" />
          Wgraj plik
        </h2>
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept=".txt,.md,.py,.js,.ts,.yaml,.yml,.json,.toml"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
        <button onClick={() => fileRef.current?.click()} className="btn-ghost flex items-center gap-2">
          <Upload size={13} />
          Wybierz plik
        </button>
        <p className="text-xs text-gray-600 mt-2">Obsługiwane: .txt, .md, .py, .js, .ts, .yaml, .json</p>
      </div>

      {/* Search */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Search size={14} className="text-accent-400" />
          Wyszukaj semantycznie
        </h2>
        <div className="flex gap-3">
          <input
            className="input"
            placeholder="Zapytanie w języku naturalnym..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
          />
          <button onClick={search} disabled={!query || searching} className="btn-primary whitespace-nowrap flex items-center gap-1.5">
            <Search size={13} />
            Szukaj
          </button>
        </div>
        {results.length > 0 && (
          <div className="mt-4 space-y-3">
            {results.map((r, i) => (
              <div key={i} className="bg-dark-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 font-mono">{String(r.metadata?.path ?? "")}</span>
                  <span className="badge-green">score: {r.score}</span>
                </div>
                <p className="text-xs text-gray-300 whitespace-pre-wrap">{r.content.slice(0, 400)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
