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

export interface StalledLift {
  exercise: string;
  template_id: string | null;
  best_est_1rm: number;
  current_est_1rm: number;
  sessions_since_pr: number;
  last_pr_date: string | null;
}

export interface VolumeRow {
  week: string;
  muscle: string;
  volume_kg: number;
}

export interface DashboardData {
  exercises: TrackedExercise[];
  stalled_lifts: StalledLift[];
  weekly_volume: VolumeRow[];
}

export interface TrendPoint {
  date: string | null;
  est_1rm: number;
  top_weight_kg: number;
  top_reps: number;
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
  exercises: ProposedExercise[];
  status?: string;
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
  trend: (exercise: string, formula = "epley") =>
    fetch(`/api/dashboard/trend?exercise=${encodeURIComponent(exercise)}&formula=${formula}`).then(
      (r) => j<{ exercise: string; formula: string; series: TrendPoint[] }>(r),
    ),
  summary: () => fetch("/api/dashboard/summary").then((r) => j<any>(r)),
  updateProposal: (id: number, payload: any) =>
    fetch(`/api/routines/proposals/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    }).then((r) => j<any>(r)),
  approveProposal: (id: number, payload?: any) =>
    fetch(`/api/routines/proposals/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ? { payload } : {}),
    }).then((r) => j<any>(r)),
};

// Stream chat via SSE, invoking onEvent for each parsed event.
export async function streamChat(
  messages: { role: string; content: string }[],
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
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
