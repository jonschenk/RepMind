import { useEffect, useState } from "react";
import { api, Health } from "./api";
import { useUnit } from "./units";
import { Dashboard } from "./views/Dashboard";
import { Chat } from "./views/Chat";
import { WeeklyReview } from "./views/WeeklyReview";

// Weight display unit toggle (settings). Persisted server-side; default LB.
function UnitToggle() {
  const { unit, setUnit } = useUnit();
  return (
    <div className="unit-toggle" title="Weight display unit">
      {(["lb", "kg"] as const).map((u) => (
        <button
          key={u}
          className={`unit-opt ${unit === u ? "active" : ""}`}
          onClick={() => setUnit(u)}
        >
          {u.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<"dashboard" | "weekly" | "chat">("dashboard");
  const [health, setHealth] = useState<Health | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  // Bumped after every sync so the active view re-fetches the freshened data.
  const [refreshKey, setRefreshKey] = useState(0);

  async function loadHealth() {
    try {
      setHealth(await api.health());
    } catch {
      setHealth(null);
    }
  }

  async function runSync(silent = false) {
    if (!silent) {
      setSyncing(true);
      setSyncMsg(null);
    }
    try {
      const r = await api.syncNow();
      if (!silent) {
        setSyncMsg(r.mode === "full" ? `Synced ${r.workouts_synced} workouts` : `Δ ${r.updated} updated, ${r.deleted} deleted`);
      }
      setRefreshKey((k) => k + 1);
      await loadHealth();
    } catch (e: any) {
      if (!silent) setSyncMsg(`Sync failed: ${e.message ?? e}`);
    } finally {
      if (!silent) setSyncing(false);
    }
  }

  // Sync on load, then every 30 min while the app stays open, so the data is current
  // without needing the manual button (which stays for an on-demand force).
  useEffect(() => {
    loadHealth();
    runSync(true);
    const id = setInterval(() => runSync(true), 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

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
        <UnitToggle />
        {health?.dry_run && <span className="pill dry">DRY RUN</span>}
        {health && <span className="pill">{health.workout_count} workouts</span>}
        {syncMsg && <span className="muted" style={{ fontSize: 12 }}>{syncMsg}</span>}
        <button className="btn ghost" onClick={() => runSync()} disabled={syncing || !health?.hevy_configured}>
          {syncing ? "Syncing…" : "Sync now"}
        </button>
      </header>

      {!health && <div className="banner">Backend unreachable — is it running on :8000?</div>}
      {health && !health.hevy_configured && (
        <div className="banner">HEVY_API_KEY is not set. Add it to .env (requires Hevy Pro) and restart the backend.</div>
      )}

      {tab === "dashboard" && <Dashboard health={health} refreshKey={refreshKey} />}
      {tab === "weekly" && <WeeklyReview anthropicReady={!!health?.anthropic_configured} />}
      {tab === "chat" && <Chat anthropicReady={!!health?.anthropic_configured} />}
    </div>
  );
}
