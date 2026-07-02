import { useEffect, useRef, useState } from "react";
import { Cuboid } from "lucide-react";
import { getHealth, streamChat } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { DataSummaryPanel } from "./components/DataSummaryPanel";
import { TracePanel } from "./components/TracePanel";
import { VisualizationPanel } from "./components/VisualizationPanel";
import type { Artifact, ChatMessage, StepRow, UploadedFile, VizData, WorkflowEvent } from "./types";

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
  const [attachments, setAttachments] = useState<UploadedFile[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [traceId, setTraceId] = useState("");
  const [running, setRunning] = useState(false);
  const [backendOk, setBackendOk] = useState(false);
  const streamingIdRef = useRef<string | null>(null);
  const answerTimerRef = useRef<number | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const hasAnswer = messages.some((message) => message.role === "assistant" && message.content.trim().length > 0);
  const hasResults = hasAnswer || Boolean(viz) || artifacts.length > 0;

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

  async function submitQuery(query: string, fileIds: string[] = []) {
    stopAnswerTextStream();
    chatAbortRef.current?.abort();
    const controller = new AbortController();
    chatAbortRef.current = controller;
    const assistantId = makeId("assistant");
    setMessages((current) => [
      ...current,
      { id: makeId("user"), role: "user", content: query },
      { id: assistantId, role: "assistant", content: "正在生成回答...", streaming: true }
    ]);
    setSteps([]);
    setViz(null);
    setArtifacts([]);
    setTraceId("");
    setRunning(true);
    streamingIdRef.current = assistantId;

    try {
      await streamChat(query, fileIds, handleWorkflowEvent, controller.signal);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      const message = err instanceof Error ? err.message : "请求失败";
      updateStreamingMessage(`后端请求失败：${message}`);
    } finally {
      if (!controller.signal.aborted) {
        setRunning(false);
      }
    }
  }

  function stopAnswerTextStream() {
    if (answerTimerRef.current !== null) {
      window.clearInterval(answerTimerRef.current);
      answerTimerRef.current = null;
    }
  }

  function updateStreamingMessage(content: string) {
    stopAnswerTextStream();
    const streamId = streamingIdRef.current;
    setMessages((current) => {
      if (streamId) {
        const idx = current.findIndex((m) => m.id === streamId);
        if (idx >= 0) {
          const next = [...current];
          next[idx] = { ...next[idx], content, streaming: false };
          return next;
        }
      }
      return [...current, { id: makeId("assistant"), role: "assistant", content }];
    });
    streamingIdRef.current = null;
  }

  function streamAnswerText(content: string) {
    stopAnswerTextStream();

    const streamId = streamingIdRef.current;
    const finalContent = content || "未生成回答。";
    if (!streamId) {
      setMessages((current) => [
        ...current,
        { id: makeId("assistant"), role: "assistant", content: finalContent }
      ]);
      return;
    }

    let cursor = 0;
    const chunkSize = finalContent.length > 600 ? 8 : 4;

    setMessages((current) => updateMessageContent(current, streamId, "", true));
    answerTimerRef.current = window.setInterval(() => {
      cursor = Math.min(cursor + chunkSize, finalContent.length);
      const visible = finalContent.slice(0, cursor);
      const done = cursor >= finalContent.length;

      if (streamingIdRef.current !== streamId) {
        // A new query arrived while streaming — discard this stale update.
        stopAnswerTextStream();
        return;
      }

      setMessages((current) => updateMessageContent(current, streamId, visible, !done));

      if (done) {
        streamingIdRef.current = null;
        stopAnswerTextStream();
      }
    }, 24);
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
      setArtifacts(event.artifacts ?? []);
      const finalAnswer = event.answer ?? "";
      streamAnswerText(finalAnswer);
      return;
    }

    if (event.type === "error") {
      updateStreamingMessage(`工作流出错：${event.detail ?? event.error_type ?? "unknown error"}`);
    }
  }

  return (
    <main className={hasResults ? "app-shell state-result" : "app-shell state-empty"}>
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
        <ChatPanel
          messages={messages}
          running={running}
          viz={viz}
          attachments={attachments}
          onAttachmentsChange={setAttachments}
          onSubmit={submitQuery}
        />
        <div className="visual-stack">
          <VisualizationPanel viz={viz} artifacts={artifacts} />
        </div>
        <aside className="right-stack">
          <TracePanel steps={steps} traceId={traceId} />
          <DataSummaryPanel viz={viz} />
        </aside>
      </div>
    </main>
  );
}

function updateMessageContent(
  messages: ChatMessage[],
  id: string,
  content: string,
  streaming: boolean
): ChatMessage[] {
  const idx = messages.findIndex((message) => message.id === id);
  if (idx < 0) {
    return messages;
  }

  const next = [...messages];
  next[idx] = { ...next[idx], content, streaming };
  return next;
}

function findLastRunningStep(rows: StepRow[], stepName: string): number {
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    if (rows[index].step_name === stepName && rows[index].status === "running") {
      return index;
    }
  }
  return -1;
}
