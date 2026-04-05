import { useState, useRef, useEffect } from "react";
import { api } from "../api/client";
import { Send, Bot, User, Loader, Info, RefreshCw } from "lucide-react";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8080";

interface Message {
  role: "user" | "assistant";
  content: string;
  contextSources?: number;
  memoryHits?: number;
  collections?: string[];
  error?: boolean;
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [useRag, setUseRag] = useState(true);
  const [useMemory, setUseMemory] = useState(true);
  const [showContext, setShowContext] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.models.list()
      .then((r) => {
        const names = (r.models ?? []).map((m) => m.name);
        setModels(names);
        if (names.length > 0) setModel(names[0]);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || sending) return;
    const userMsg = input.trim();
    setInput("");
    setSending(true);

    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      // Streaming chat
      const res = await fetch(`${BASE}/api/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg,
          model,
          session_id: sessionId,
          use_rag: useRag,
          use_memory: useMemory,
          stream: true,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body?.getReader();
      if (!reader) throw new Error("Brak stream");

      const dec = new TextDecoder();
      let fullText = "";
      let contextSources = 0;
      let memoryHits = 0;
      let collections: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = dec.decode(value).split("\n").filter(Boolean);
        for (const line of lines) {
          try {
            const data = JSON.parse(line);
            if (data.token !== undefined) {
              fullText += data.token;
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = {
                  role: "assistant",
                  content: fullText,
                };
                return next;
              });
            }
            if (data.context_sources !== undefined) contextSources = data.context_sources;
            if (data.memory_hits !== undefined) memoryHits = data.memory_hits;
            if (data.collections !== undefined) collections = data.collections;
          } catch {}
        }
      }

      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: fullText || "(brak odpowiedzi)",
          contextSources,
          memoryHits,
          collections,
        };
        return next;
      });

    } catch (e) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: `Błąd: ${e}`,
          error: true,
        };
        return next;
      });
    } finally {
      setSending(false);
    }
  };

  const previewContext = async () => {
    if (!input.trim()) return;
    try {
      const r = await fetch(`${BASE}/api/chat/context-preview?query=${encodeURIComponent(input)}&n=5`);
      const data = await r.json();
      alert(
        `Kontekst dla: "${input}"\n\n` +
        `Fragmenty kodu/docs: ${data.knowledge_chunks}\n` +
        `Wspomnienia: ${data.memory_chunks}\n` +
        `Kolekcje: ${data.collections_searched?.join(", ") || "brak"}\n\n` +
        `System prompt (pierwsze 500 znaków):\n${data.system_prompt_preview?.slice(0, 500)}...`
      );
    } catch (e) {
      alert(`Błąd: ${e}`);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -mx-6 -mt-8">
      {/* Header */}
      <div className="px-6 py-4 border-b border-dark-500 bg-dark-800 flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-lg font-bold text-gray-100">Chat z pamięcią</h1>
          <p className="text-xs text-gray-500">Model widzi Twoje repo, dokumenty i poprzednie rozmowy</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Model selector */}
          <select
            className="bg-dark-600 border border-dark-500 rounded-lg px-2 py-1.5 text-xs text-gray-300 focus:outline-none"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {models.length === 0 && <option value="">Brak modeli</option>}
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>

          {/* Toggles */}
          <Toggle label="RAG" active={useRag} onChange={setUseRag} />
          <Toggle label="Pamięć" active={useMemory} onChange={setUseMemory} />

          {/* Clear */}
          <button
            onClick={() => setMessages([])}
            className="text-gray-500 hover:text-gray-300 transition-colors"
            title="Wyczyść czat"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Bot size={40} className="text-accent-500/40 mb-3" />
            <p className="text-gray-400 text-sm">
              Zacznij rozmowę. Model automatycznie przeszuka<br />
              Twoje repozytoria, dokumenty i poprzednie rozmowy.
            </p>
            {useRag && (
              <p className="text-xs text-gray-600 mt-2">
                RAG aktywny — pytaj o swój kod bezpośrednio
              </p>
            )}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            {msg.role === "assistant" && (
              <div className="w-7 h-7 rounded-full bg-accent-500/20 flex items-center justify-center shrink-0 mt-0.5">
                <Bot size={14} className="text-accent-400" />
              </div>
            )}
            <div className={`max-w-[80%] ${msg.role === "user" ? "items-end" : "items-start"} flex flex-col gap-1`}>
              <div className={`rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-accent-500 text-white"
                  : msg.error
                  ? "bg-red-900/30 border border-red-700/50 text-red-300"
                  : "bg-dark-700 border border-dark-500 text-gray-200"
              }`}>
                {msg.content || (sending && i === messages.length - 1 ? <Loader size={14} className="animate-spin" /> : "…")}
              </div>
              {/* Context badges */}
              {msg.role === "assistant" && (msg.contextSources || msg.memoryHits) ? (
                <div className="flex gap-1.5 flex-wrap">
                  {(msg.contextSources ?? 0) > 0 && (
                    <span className="badge-blue text-[10px]">
                      {msg.contextSources} źródeł kodu
                    </span>
                  )}
                  {(msg.memoryHits ?? 0) > 0 && (
                    <span className="badge-green text-[10px]">
                      {msg.memoryHits} wspomnień
                    </span>
                  )}
                  {msg.collections?.map((c) => (
                    <span key={c} className="text-[10px] text-gray-600">{c}</span>
                  ))}
                </div>
              ) : null}
            </div>
            {msg.role === "user" && (
              <div className="w-7 h-7 rounded-full bg-dark-500 flex items-center justify-center shrink-0 mt-0.5">
                <User size={14} className="text-gray-400" />
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-dark-500 bg-dark-800 shrink-0">
        <div className="flex gap-3">
          <button
            onClick={previewContext}
            title="Podgląd kontekstu RAG"
            className="text-gray-600 hover:text-accent-400 transition-colors shrink-0"
          >
            <Info size={16} />
          </button>
          <textarea
            className="input resize-none h-12 min-h-12 max-h-40"
            placeholder="Napisz coś... (Enter = wyślij, Shift+Enter = nowa linia)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || sending || !model}
            className="btn-primary shrink-0 flex items-center gap-1.5"
          >
            {sending ? <Loader size={14} className="animate-spin" /> : <Send size={14} />}
          </button>
        </div>
      </div>
    </div>
  );
}

function Toggle({ label, active, onChange }: { label: string; active: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!active)}
      className={`text-xs px-2 py-1 rounded border transition-colors ${
        active
          ? "border-accent-500/50 bg-accent-500/10 text-accent-300"
          : "border-dark-500 text-gray-600 hover:text-gray-400"
      }`}
    >
      {label}
    </button>
  );
}
