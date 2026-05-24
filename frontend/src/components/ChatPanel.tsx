import { FormEvent, useState } from "react";
import { Send, SquareActivity } from "lucide-react";
import type { ChatMessage } from "../types";

interface ChatPanelProps {
  messages: ChatMessage[];
  running: boolean;
  onSubmit: (query: string) => void;
}

export function ChatPanel({ messages, running, onSubmit }: ChatPanelProps) {
  const [draft, setDraft] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = draft.trim();
    if (!value || running) {
      return;
    }
    setDraft("");
    onSubmit(value);
  }

  return (
    <section className="panel chat-panel" aria-label="对话">
      <div className="panel-head">
        <div>
          <span className="eyebrow">A</span>
          <h2>对话</h2>
        </div>
        <span className={running ? "status-pill live" : "status-pill"}>
          <SquareActivity size={14} />
          {running ? "运行中" : "就绪"}
        </span>
      </div>

      <div className="message-list">
        {messages.length === 0 ? (
          <div className="empty-state compact">
            <strong>材料分析控制台</strong>
            <span>输入 MP-ID、化学式或筛选条件。</span>
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className={`message ${message.role}`}>
              <div className="message-role">{message.role === "user" ? "你" : "Agent"}</div>
              <p>{message.content}</p>
            </article>
          ))
        )}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="例如：展示 LiFePO4 的晶体结构和 XRD"
          disabled={running}
        />
        <button type="submit" disabled={running || !draft.trim()} aria-label="发送">
          <Send size={18} />
        </button>
      </form>
    </section>
  );
}
