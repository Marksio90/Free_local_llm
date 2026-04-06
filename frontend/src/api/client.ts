const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8080";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Models ─────────────────────────────────────
export const api = {
  models: {
    list: () => request<{ models: ModelInfo[] }>("/api/models/"),
    pull: (model_name: string) =>
      fetch(`${BASE}/api/models/pull`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_name }),
      }),
    delete: (name: string) => request(`/api/models/${name}`, { method: "DELETE" }),
    generate: (model: string, prompt: string, system?: string) =>
      request<{ response: string }>("/api/models/generate", {
        method: "POST",
        body: JSON.stringify({ model, prompt, system: system ?? "" }),
      }),
  },

  // ── Knowledge ────────────────────────────────
  knowledge: {
    collections: () => request<CollectionInfo[]>("/api/knowledge/collections"),
    deleteCollection: (name: string) =>
      request(`/api/knowledge/collections/${name}`, { method: "DELETE" }),
    search: (query: string, collection: string, n = 5) =>
      request<{ results: SearchResult[] }>("/api/knowledge/search", {
        method: "POST",
        body: JSON.stringify({ query, collection_name: collection, n_results: n }),
      }),
    addText: (text: string, source: string, collection = "documents") =>
      request("/api/knowledge/add-text", {
        method: "POST",
        body: JSON.stringify({ text, source, collection_name: collection }),
      }),
    upload: async (file: File, collection = "documents") => {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(`${BASE}/api/knowledge/upload?collection_name=${collection}`, {
        method: "POST",
        body: fd,
      });
      if (!r.ok) {
        const err = await r.text();
        throw new Error(err || `HTTP ${r.status}`);
      }
      return r.json();
    },
  },

  // ── GitHub ───────────────────────────────────
  github: {
    ingest: (repo_url: string, collection_name?: string) =>
      request<IngestJob>("/api/github/ingest", {
        method: "POST",
        body: JSON.stringify({ repo_url, collection_name: collection_name ?? "" }),
      }),
    jobStatus: (id: string) => request<IngestJob>(`/api/github/jobs/${id}`),
    jobs: () => request<IngestJob[]>("/api/github/jobs"),
    search: (query: string, collection: string, n = 5) =>
      request<{ results: SearchResult[] }>("/api/github/search", {
        method: "POST",
        body: JSON.stringify({ query, collection_name: collection, n_results: n }),
      }),
  },

  // ── Training ─────────────────────────────────
  training: {
    buildDataset: (collection: string, output_name: string, max_samples: number, model: string) =>
      request<{ job_id: string }>("/api/training/dataset/build", {
        method: "POST",
        body: JSON.stringify({ collection_name: collection, output_name, max_samples, model }),
      }),
    datasets: () => request<DatasetInfo[]>("/api/training/datasets"),
    jobs: () => request<TrainingJob[]>("/api/training/jobs"),
    jobStatus: (id: string) => request<TrainingJob>(`/api/training/jobs/${id}`),
    instructions: () => request<FineTuneInstructions>("/api/training/instructions"),
    learnStatus: () => request<LearnStatus>("/api/training/learn/status"),
    triggerLearn: () => request<{ status: string; message: string }>("/api/training/learn/trigger", { method: "POST" }),
  },

  health: () => request<{ status: string }>("/health"),
};

// ── Types ─────────────────────────────────────
export interface ModelInfo {
  name: string;
  size: number;
  modified_at: string;
  details?: { parameter_size?: string; quantization_level?: string };
}

export interface CollectionInfo {
  name: string;
  count: number;
}

export interface SearchResult {
  content: string;
  metadata: Record<string, unknown>;
  score: number;
}

export interface IngestJob {
  status: string;
  repo?: string;
  ingested?: number;
  total_files?: number;
  error?: string;
}

export interface DatasetInfo {
  name: string;
  path: string;
  size_kb: number;
  samples: number;
}

export interface TrainingJob {
  status: string;
  step?: string;
  pairs_generated?: number;
  file?: string;
  error?: string;
}

export interface FineTuneInstructions {
  info: string;
  steps: string[];
  without_gpu: string;
}

export interface LearnStatus {
  running: boolean;
  last_learn: string | null;
  learned_repos: string[];
  pending_repos: string[];
  wiki_topics_learned: string[];
  total_samples: number;
  last_dataset: string | null;
  gpu_training_done: boolean;
  log: string[];
}
