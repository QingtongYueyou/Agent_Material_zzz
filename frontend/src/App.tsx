import { useEffect, useRef, useState } from "react";
import { Cuboid } from "lucide-react";
import { getHealth, streamChat } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { DataSummaryPanel } from "./components/DataSummaryPanel";
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
  const streamingIdRef = useRef<string | null>(null);
  const hasAnswer = messages.some((message) => message.role === "assistant" && message.content.trim().length > 0);

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

  async function submitQuery(query: string) {
    setMessages((current) => [...current, { id: makeId("user"), role: "user", content: query }]);
    setSteps([]);
    setViz(null);
    setTraceId("");
    setRunning(true);
    streamingIdRef.current = null;

    try {
      await streamChat(query, handleWorkflowEvent);
    } catch (err) {
      const message = err instanceof Error ? err.message : "请求失败";
      setMessages((current) => [
        ...current,
        { id: makeId("assistant"), role: "assistant", content: `后端请求失败：${message}` }
      ]);
    } finally {
      streamingIdRef.current = null;
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

    if (event.type === "answer_delta") {
      const delta = event.delta ?? "";
      if (!delta) return;

      setMessages((current) => {
        const id = streamingIdRef.current;
        if (id) {
          const idx = current.findIndex((m) => m.id === id);
          if (idx >= 0) {
            const next = [...current];
            next[idx] = { ...next[idx], content: next[idx].content + delta };
            return next;
          }
        }
        const newId = makeId("assistant");
        streamingIdRef.current = newId;
        return [...current, { id: newId, role: "assistant", content: delta, streaming: true }];
      });
      return;
    }

    if (event.type === "final") {
      setTraceId(event.trace_id ?? "");
      setViz(event.viz ?? null);
      const finalAnswer = event.answer ?? "";
      const streamId = streamingIdRef.current;

      setMessages((current) => {
        if (streamId) {
          const idx = current.findIndex((m) => m.id === streamId);
          if (idx >= 0) {
            const next = [...current];
            next[idx] = { ...next[idx], content: finalAnswer || next[idx].content, streaming: false };
            return next;
          }
        }
        return [...current, { id: makeId("assistant"), role: "assistant", content: finalAnswer }];
      });
      streamingIdRef.current = null;
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
    <main className={hasAnswer || viz ? "app-shell state-result" : "app-shell state-empty"}>
      <header className="top-bar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <Cuboid size={36} strokeWidth={2.4} />
          </span>
          <span className="brand-divider" aria-hidden="true" />
          <h1>材料智能分析系统</h1>
        </div>
        <div className="top-status">
          <span className="product-name">MATERIAL AI ANALYSIS</span>
          <span className="version-pill">v2.0</span>
          <span className={backendOk ? "system-state good" : "system-state bad"}>
            <i aria-hidden="true" />
            {backendOk ? "系统运行正常" : "系统连接异常"}
          </span>
        </div>
      </header>

      <div className="main-grid">
        <ChatPanel messages={messages} running={running} viz={viz} onSubmit={submitQuery} />
        <VisualizationPanel viz={viz} />
        <aside className="right-stack">
          <TracePanel steps={steps} traceId={traceId} />
          <DataSummaryPanel viz={viz} />
        </aside>
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
