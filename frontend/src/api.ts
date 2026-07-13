// Typed client for the repMind backend. Frontend talks ONLY to the backend — it never
// sees the Hevy or Anthropic keys.

export interface Health {
  status: string;
  hevy_configured: boolean;
  anthropic_configured: boolean;
  dry_run: boolean;
  model: string;
  full_sync_done: boolean;
  workout_count: number;
}

export interface TrackedExercise {
  exercise: string;
  template_id: string | null;
  sessions: number;
}

export interface RepMix {
  strength: number;
  hypertrophy: number;
  endurance: number;
  total_sets: number;
}

export type Verdict = "progressing" | "holding" | "regressing" | "new";

export interface ProgressionItem {
  exercise: string;
  template_id: string | null;
  sessions: number;
  verdict: Verdict;
  reason: string;
  rep_mix: RepMix;
  best_est_1rm: number | null;
  volume_change_pct?: number;
  recent_best_set?: { weight_kg: number; reps: number };
}

export interface VolumeRow {
  week: string;
  muscle: string;
  volume_kg: number;
}

export interface BodyStats {
  has_data: boolean;
  latest?: { date: string; weight_kg: number; fat_percent: number | null };
  days_since?: number | null;
  stale?: boolean;
  target_lb: number[];
  trend?: { date: string; weight_kg: number; fat_percent: number | null }[];
  relative_strength?: { exercise: string; est_1rm_kg: number; ratio: number }[];
}

export interface DashboardData {
  exercises: TrackedExercise[];
  progression: ProgressionItem[];
  training_mix: RepMix;
  weekly_volume: VolumeRow[];
}

export interface TrendSeriesPoint {
  label: string;
  value: number | null;
  reps?: number;
}

export interface TrendResponse {
  exercise: string;
  est_1rm: TrendSeriesPoint[];
  top_set: TrendSeriesPoint[];
  volume: TrendSeriesPoint[];
}

export interface ProposedSet {
  type: string;
  weight_kg?: number;
  reps?: number;
}
export interface ProposedExercise {
  name: string;
  rest_seconds?: number;
  notes?: string;
  sets: ProposedSet[];
}
export interface Proposal {
  id: number;
  title: string;
  notes?: string;
  folder?: string;
  exercises: ProposedExercise[];
  status?: string;
  kind?: string; // "create" | "update"
  change_summary?: string;
}

export interface WeeklyProposal {
  id: number;
  kind: "create" | "update";
  target_routine_id: string | null;
  title: string;
  diff: { rationale?: string; changes_summary?: string } | null;
  payload: { title: string; notes?: string; folder?: string; exercises: ProposedExercise[] };
  status: string;
}

export interface VolumeReportRow {
  muscle: string;
  sets: number;
  mev: number;
  mav: number;
  status: string;
  priority?: boolean;
}

export interface WeeklyReviewData {
  exists: boolean;
  id?: number;
  generated_at?: string;
  period?: { start: string; end: string };
  narrative?: string;
  signals?: {
    training_days: number;
    training_mix: RepMix;
    muscle_volume: VolumeReportRow[];
    progression: ProgressionItem[];
    est_1rm_prs: { exercise: string; est_1rm: number; prev_best: number; gain: number; date: string }[];
    notes: { category: string; exercise: string | null; quote: string; insight: string }[];
  };
  proposals?: WeeklyProposal[];
}

export type ChatEvent =
  | { type: "text"; text: string }
  | { type: "tool_use"; name: string; input: unknown }
  | { type: "proposal"; proposal: Proposal }
  | { type: "done" }
  | { type: "error"; message: string };

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch("/api/health").then((r) => j<Health>(r)),
  syncStatus: () => fetch("/api/sync/status").then((r) => j<any>(r)),
  syncNow: () => fetch("/api/sync", { method: "POST" }).then((r) => j<any>(r)),
  dashboard: () => fetch("/api/dashboard").then((r) => j<DashboardData>(r)),
  trend: (exercise: string) =>
    fetch(`/api/dashboard/trend?exercise=${encodeURIComponent(exercise)}`).then((r) =>
      j<TrendResponse>(r),
    ),
  summary: () => fetch("/api/dashboard/summary").then((r) => j<any>(r)),
  body: () => fetch("/api/dashboard/body").then((r) => j<BodyStats>(r)),
  updateProposal: (id: number, payload: any) =>
    fetch(`/api/routines/proposals/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    }).then((r) => j<any>(r)),
  dismissProposal: (id: number) =>
    fetch(`/api/routines/proposals/${id}/dismiss`, { method: "POST" }).then((r) => j<any>(r)),
  approveProposal: (id: number, payload?: any) =>
    fetch(`/api/routines/proposals/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ? { payload } : {}),
    }).then((r) => j<any>(r)),
  weeklyReview: () => fetch("/api/weekly").then((r) => j<WeeklyReviewData>(r)),
  generateWeekly: () => fetch("/api/weekly/generate", { method: "POST" }).then((r) => j<any>(r)),
  chatHistory: () =>
    fetch("/api/chat/history").then((r) =>
      j<{ role: string; content: string; proposals: Proposal[] }[]>(r),
    ),
};

// Stream chat via SSE, invoking onEvent for each parsed event. History lives server-side
// (memory), so we only send the new message.
export async function streamChat(
  message: string,
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as ChatEvent);
      } catch {
        // ignore malformed keepalive lines
      }
    }
  }
}
