import { useEffect, useMemo, useState } from "react";
import { DatabaseZap, Server, ShieldCheck } from "lucide-react";
import { getHealth, streamChat } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { TracePanel } from "./components/TracePanel";
import { VisualizationPanel } from "./components/VisualizationPanel";
import type { ChatMessage, StepRow, VizData, WorkflowEvent } from "./types";

function makeId(prefix: string): string {
  if (crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [steps, setSteps] = useState<StepRow[]>([]);
  const [viz, setViz] = useState<VizData | null>(null);
  const [traceId, setTraceId] = useState("");
  const [running, setRunning] = useState(false);
  const [backendOk, setBackendOk] = useState(false);

  useEffect(() => {
    getHealth()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, []);

  useEffect(() => {
    if (!import.meta.env.DEV) {
      return;
    }

    const demoViz = new URLSearchParams(window.location.search).get("demoViz");
    if (!demoViz) {
      return;
    }

    setViz({
      filename: demoViz,
      lattice: [],
      composition: [],
      xrd: []
    });
  }, []);

  const latestMaterial = useMemo(() => {
    if (!viz?.filename) {
      return "未选择";
    }
    return viz.filename.replace(/\.cif$/i, "");
  }, [viz?.filename]);

  async function submitQuery(query: string) {
    setMessages((current) => [...current, { id: makeId("user"), role: "user", content: query }]);
    setSteps([]);
    setViz(null);
    setTraceId("");
    setRunning(true);

    try {
      await streamChat(query, handleWorkflowEvent);
    } catch (err) {
      const message = err instanceof Error ? err.message : "请求失败";
      setMessages((current) => [
        ...current,
        { id: makeId("assistant"), role: "assistant", content: `后端请求失败：${message}` }
      ]);
    } finally {
      setRunning(false);
    }
  }

  function handleWorkflowEvent(event: WorkflowEvent) {
    if (event.type === "step_start" && event.step) {
      setSteps((current) => [
        ...current,
        {
          id: makeId("step"),
          step_name: event.step ?? "unknown",
          status: "running"
        }
      ]);
      return;
    }

    if (event.type === "step_end" && event.step) {
      setSteps((current) => {
        const next = [...current];
        const index = findLastRunningStep(next, event.step ?? "");
        const row: StepRow = {
          id: index >= 0 ? next[index].id : makeId("step"),
          step_name: event.step ?? "unknown",
          status: event.status ?? "success",
          latency_ms: event.latency_ms,
          error_message: event.error,
          fallback_used: event.fallback_used
        };

        if (index >= 0) {
          next[index] = row;
          return next;
        }
        return [...next, row];
      });
      return;
    }

    if (event.type === "final") {
      setTraceId(event.trace_id ?? "");
      setViz(event.viz ?? null);
      setMessages((current) => [
        ...current,
        { id: makeId("assistant"), role: "assistant", content: event.answer ?? "" }
      ]);
      return;
    }

    if (event.type === "error") {
      setMessages((current) => [
        ...current,
        {
          id: makeId("assistant"),
          role: "assistant",
          content: `工作流出错：${event.detail ?? event.error_type ?? "unknown error"}`
        }
      ]);
    }
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand-lockup">
          <DatabaseZap size={24} />
          <div>
            <h1>Agent Material Console</h1>
            <span>{latestMaterial}</span>
          </div>
        </div>
        <div className="top-status">
          <span className={backendOk ? "health good" : "health bad"}>
            <Server size={15} />
            Backend
          </span>
          <span className="health">
            <ShieldCheck size={15} />
            Frontend separated
          </span>
        </div>
      </header>

      <div className="main-grid">
        <ChatPanel messages={messages} running={running} onSubmit={submitQuery} />
        <VisualizationPanel viz={viz} />
        <TracePanel steps={steps} traceId={traceId} />
      </div>
    </main>
  );
}

function findLastRunningStep(rows: StepRow[], stepName: string): number {
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    if (rows[index].step_name === stepName && rows[index].status === "running") {
      return index;
    }
  }
  return -1;
}
