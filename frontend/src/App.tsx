import { useEffect, useState } from "react";
import { api, Health } from "./api";
import { Dashboard } from "./views/Dashboard";
import { Chat } from "./views/Chat";
import { WeeklyReview } from "./views/WeeklyReview";

export default function App() {
  const [tab, setTab] = useState<"dashboard" | "weekly" | "chat">("dashboard");
  const [health, setHealth] = useState<Health | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  async function loadHealth() {
    try {
      setHealth(await api.health());
    } catch {
      setHealth(null);
    }
  }

  useEffect(() => {
    loadHealth();
  }, []);

  async function sync() {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const r = await api.syncNow();
      setSyncMsg(r.mode === "full" ? `Synced ${r.workouts_synced} workouts` : `Δ ${r.updated} updated, ${r.deleted} deleted`);
      await loadHealth();
    } catch (e: any) {
      setSyncMsg(`Sync failed: ${e.message ?? e}`);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="app">
      <header className="top">
        <h1>
          <span className="logo">rep</span>Mind
        </h1>
        <div className="tabs">
          <button className={`tab ${tab === "dashboard" ? "active" : ""}`} onClick={() => setTab("dashboard")}>
            Dashboard
          </button>
          <button className={`tab ${tab === "weekly" ? "active" : ""}`} onClick={() => setTab("weekly")}>
            Weekly
          </button>
          <button className={`tab ${tab === "chat" ? "active" : ""}`} onClick={() => setTab("chat")}>
            Chat
          </button>
        </div>
        <div className="spacer" />
        {health?.dry_run && <span className="pill dry">DRY RUN</span>}
        {health && <span className="pill">{health.workout_count} workouts</span>}
        {syncMsg && <span className="muted" style={{ fontSize: 12 }}>{syncMsg}</span>}
        <button className="btn ghost" onClick={sync} disabled={syncing || !health?.hevy_configured}>
          {syncing ? "Syncing…" : "Sync now"}
        </button>
      </header>

      {!health && <div className="banner">Backend unreachable — is it running on :8000?</div>}
      {health && !health.hevy_configured && (
        <div className="banner">HEVY_API_KEY is not set. Add it to .env (requires Hevy Pro) and restart the backend.</div>
      )}

      {tab === "dashboard" && <Dashboard health={health} />}
      {tab === "weekly" && <WeeklyReview anthropicReady={!!health?.anthropic_configured} />}
      {tab === "chat" && <Chat anthropicReady={!!health?.anthropic_configured} />}
    </div>
  );
}
