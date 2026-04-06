import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "../api/client";
import { Send, Bot, Loader, ChevronDown, Zap, Brain, Globe, StopCircle } from "lucide-react";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8080";

interface Message {
  role: "user" | "assistant";
  content: string;
  contextSources?: number;
  memoryHits?: number;
  error?: boolean;
  streaming?: boolean;
}

// Simple markdown-like rendering (no deps needed)
function MsgContent({ text, streaming }: { text: string; streaming?: boolean }) {
  if (!text && streaming) {
    return <span className="inline-block w-2 h-4 bg-accent-400 animate-pulse rounded-sm" />;
  }

  // Split into code blocks and text
  const parts = text.split(/(```[\s\S]*?```|`[^`]+`)/g);

  return (
    <span>
      {parts.map((part, i) => {
        if (part.startsWith("```")) {
          const lines = part.slice(3).split("\n");
          const lang = lines[0];
          const code = lines.slice(1).join("\n").replace(/```$/, "").trimEnd();
          return (
            <pre key={i} className="my-2 bg-dark-900 border border-dark-500 rounded-lg p-3 overflow-x-auto text-xs">
              {lang && <div className="text-gray-500 text-[10px] mb-1.5 uppercase tracking-wider">{lang}</div>}
              <code className="text-green-300 font-mono">{code}</code>
            </pre>
          );
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code key={i} className="bg-dark-900 text-green-300 px-1.5 py-0.5 rounded text-[0.85em] font-mono">
              {part.slice(1, -1)}
            </code>
          );
        }
        // Bold, italic, newlines
        return (
          <span key={i}>
            {part.split("\n").map((line, j, arr) => {
              const formatted = line
                .replace(/\*\*(.+?)\*\*/g, "##BOLD##$1##ENDBOLD##")
                .replace(/\*(.+?)\*/g, "##EM##$1##ENDEM##");
              const segments = formatted.split(/(##BOLD##.+?##ENDBOLD##|##EM##.+?##ENDEM##)/g);
              return (
                <span key={j}>
                  {segments.map((s, k) => {
                    if (s.startsWith("##BOLD##"))
                      return <strong key={k} className="font-semibold text-gray-100">{s.slice(8, -10)}</strong>;
                    if (s.startsWith("##EM##"))
                      return <em key={k} className="italic text-gray-300">{s.slice(6, -8)}</em>;
                    return <span key={k}>{s}</span>;
                  })}
                  {j < arr.length - 1 && <br />}
                </span>
              );
            })}
          </span>
        );
      })}
      {streaming && <span className="inline-block w-2 h-4 bg-accent-400 animate-pulse rounded-sm ml-0.5 align-middle" />}
    </span>
  );
}

const SUGGESTIONS: string[] = [];

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId] = useState(() => `s_${Date.now()}`);
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [useRag, setUseRag] = useState(true);
  const [useMemory, setUseMemory] = useState(true);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [bgActivity, setBgActivity] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api.models.list()
      .then((r) => {
        const names = (r.models ?? []).map((m: { name: string }) => m.name);
        setModels(names);
        if (names.length > 0) setModel(names[0]);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [input]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setSending(false);
  }, []);

  const send = useCallback(async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || sending) return;
    setInput("");
    setSending(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    setMessages((prev) => [
      ...prev,
      { role: "user", content: msg },
      { role: "assistant", content: "", streaming: true },
    ]);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const res = await fetch(`${BASE}/api/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abort.signal,
        body: JSON.stringify({
          message: msg,
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

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of dec.decode(value).split("\n").filter(Boolean)) {
          try {
            const data = JSON.parse(line);
            if (data.token !== undefined) {
              fullText += data.token;
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = { role: "assistant", content: fullText, streaming: true };
                return next;
              });
            }
            if (data.context_sources !== undefined) contextSources = data.context_sources;
            if (data.memory_hits !== undefined) memoryHits = data.memory_hits;
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
          streaming: false,
        };
        return next;
      });

      // Show background learning indicator briefly
      if (contextSources > 0 || memoryHits > 0) {
        setBgActivity(`Uczę się z rozmowy w tle...`);
        setTimeout(() => setBgActivity(null), 3000);
      }

    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") {
        setMessages((prev) => {
          const next = [...prev];
          if (next[next.length - 1]?.streaming) {
            next[next.length - 1] = { ...next[next.length - 1], streaming: false };
          }
          return next;
        });
      } else {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            content: `Błąd połączenia z modelem. Sprawdź czy Ollama działa.\n\n${e}`,
            error: true,
            streaming: false,
          };
          return next;
        });
      }
    } finally {
      setSending(false);
    }
  }, [input, sending, model, sessionId, useRag, useMemory]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-screen bg-dark-900">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-dark-500/50 bg-dark-800/80 backdrop-blur-sm shrink-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-accent-500/20 flex items-center justify-center">
            <Bot size={15} className="text-accent-400" />
          </div>
          <span className="text-sm font-medium text-gray-200">Free Local LLM</span>
          <span className="text-xs text-gray-600">v3.0</span>
        </div>

        <div className="flex items-center gap-2">
          {/* Background activity indicator */}
          {bgActivity && (
            <div className="flex items-center gap-1.5 text-[11px] text-accent-400 animate-pulse">
              <Zap size={11} />
              {bgActivity}
            </div>
          )}

          {/* RAG + Memory toggles */}
          <button
            onClick={() => setUseRag(!useRag)}
            title="Wiedza — korzysta z wyuczonej wiedzy"
            className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded border transition-colors ${
              useRag ? "border-accent-500/40 bg-accent-500/10 text-accent-300" : "border-dark-500 text-gray-600"
            }`}
          >
            <Globe size={11} />
            RAG
          </button>
          <button
            onClick={() => setUseMemory(!useMemory)}
            title="Pamięć — poprzednie rozmowy"
            className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded border transition-colors ${
              useMemory ? "border-accent-500/40 bg-accent-500/10 text-accent-300" : "border-dark-500 text-gray-600"
            }`}
          >
            <Brain size={11} />
            Pamięć
          </button>

          {/* Model picker */}
          <div className="relative">
            <button
              onClick={() => setShowModelPicker(!showModelPicker)}
              className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded border border-dark-500 text-gray-400 hover:text-gray-200 hover:border-dark-400 transition-colors"
            >
              {model || "brak modelu"}
              <ChevronDown size={11} />
            </button>
            {showModelPicker && (
              <div className="absolute right-0 top-8 bg-dark-700 border border-dark-500 rounded-lg shadow-xl z-50 min-w-48 py-1">
                {models.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-gray-500">Brak modeli. Pobierz model w ustawieniach.</div>
                ) : (
                  models.map((m) => (
                    <button
                      key={m}
                      onClick={() => { setModel(m); setShowModelPicker(false); }}
                      className={`w-full text-left px-3 py-2 text-xs hover:bg-dark-600 transition-colors ${
                        m === model ? "text-accent-300" : "text-gray-300"
                      }`}
                    >
                      {m}
                    </button>
                  ))
                )}
                <div className="border-t border-dark-500 mt-1 pt-1">
                  <a
                    href="/models"
                    className="block px-3 py-2 text-xs text-gray-500 hover:text-accent-300 transition-colors"
                  >
                    + Pobierz nowy model
                  </a>
                </div>
              </div>
            )}
          </div>

          {/* Settings link → panel admin */}
          <a
            href="/dashboard"
            className="text-[11px] px-2.5 py-1 rounded border border-dark-500 text-gray-500 hover:text-gray-300 hover:border-dark-400 transition-colors"
            title="Panel administracyjny"
          >
            ⚙
          </a>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto" onClick={() => setShowModelPicker(false)}>
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full gap-6 px-4 pb-20">
            <div className="text-center">
              <div className="w-14 h-14 rounded-2xl bg-accent-500/15 border border-accent-500/20 flex items-center justify-center mx-auto mb-4">
                <Bot size={28} className="text-accent-400" />
              </div>
              <h2 className="text-xl font-semibold text-gray-200 mb-1">Jak mogę pomóc?</h2>
              <p className="text-sm text-gray-500 max-w-sm">
                Pamiętam nasze rozmowy i automatycznie zbieram wiedzę z internetu — za darmo.
              </p>
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "assistant" && (
                  <div className="w-7 h-7 rounded-lg bg-accent-500/20 flex items-center justify-center shrink-0 mt-0.5">
                    <Bot size={14} className="text-accent-400" />
                  </div>
                )}

                <div className={`flex flex-col gap-1 ${msg.role === "user" ? "items-end max-w-[75%]" : "items-start max-w-[85%]"}`}>
                  <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-accent-500 text-white rounded-br-sm"
                      : msg.error
                      ? "bg-red-950/50 border border-red-800/50 text-red-300 rounded-bl-sm"
                      : "bg-dark-700 border border-dark-500/50 text-gray-200 rounded-bl-sm"
                  }`}>
                    <MsgContent text={msg.content} streaming={msg.streaming} />
                  </div>

                  {/* Context badges — subtle, below message */}
                  {msg.role === "assistant" && !msg.streaming && ((msg.contextSources ?? 0) > 0 || (msg.memoryHits ?? 0) > 0) && (
                    <div className="flex gap-2 px-1">
                      {(msg.contextSources ?? 0) > 0 && (
                        <span className="flex items-center gap-1 text-[10px] text-gray-600">
                          <Globe size={9} />
                          {msg.contextSources} wiedzy
                        </span>
                      )}
                      {(msg.memoryHits ?? 0) > 0 && (
                        <span className="flex items-center gap-1 text-[10px] text-gray-600">
                          <Brain size={9} />
                          {msg.memoryHits} wspomnień
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {msg.role === "user" && (
                  <div className="w-7 h-7 rounded-lg bg-dark-600 flex items-center justify-center shrink-0 mt-0.5 text-xs text-gray-500 font-medium">
                    Ty
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} className="h-4" />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="shrink-0 border-t border-dark-500/50 bg-dark-800/80 backdrop-blur-sm px-4 py-3">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-2 bg-dark-700 border border-dark-500 rounded-2xl px-4 py-3 focus-within:border-accent-500/60 transition-colors">
            <textarea
              ref={textareaRef}
              className="flex-1 bg-transparent text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none min-h-[24px] max-h-[200px] leading-relaxed"
              placeholder={model ? "Napisz wiadomość..." : "Brak modelu — pobierz model w ustawieniach (⚙)"}
              value={input}
              disabled={!model}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={1}
            />
            {sending ? (
              <button
                onClick={stop}
                className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                title="Zatrzymaj"
              >
                <StopCircle size={16} />
              </button>
            ) : (
              <button
                onClick={() => send()}
                disabled={!input.trim() || !model}
                className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg bg-accent-500 text-white hover:bg-accent-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                {sending ? <Loader size={15} className="animate-spin" /> : <Send size={15} />}
              </button>
            )}
          </div>
          <p className="text-[10px] text-gray-700 text-center mt-1.5">
            Enter = wyślij · Shift+Enter = nowa linia · RAG + Pamięć = {useRag && useMemory ? "aktywne" : useRag ? "tylko RAG" : useMemory ? "tylko pamięć" : "wyłączone"}
          </p>
        </div>
      </div>
    </div>
  );
}
