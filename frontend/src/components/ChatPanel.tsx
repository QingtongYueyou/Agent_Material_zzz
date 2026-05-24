import { FormEvent, useState } from "react";
import { MessageCircleMore, SendHorizontal, Sparkles } from "lucide-react";
import Markdown from "react-markdown";
import type { ChatMessage, VizData } from "../types";

interface ChatPanelProps {
  messages: ChatMessage[];
  running: boolean;
  viz: VizData | null;
  onSubmit: (query: string) => void;
}

export function ChatPanel({ messages, running, viz, onSubmit }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const lastUserMessage = [...messages].reverse().find((message) => message.role === "user");
  const lastAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant");
  const hasResult = Boolean(lastAssistantMessage?.content.trim() || viz);

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
    <section className="panel chat-panel" aria-label="对话与控制">
      <div className="chat-head">
        <div className="section-title">
          <span className="section-icon chat-icon">
            <MessageCircleMore size={19} />
          </span>
          <h2>对话与控制</h2>
        </div>
        <span className={running ? "status-pill live" : "status-pill"}>
          <i aria-hidden="true" />
          {running ? "运行中" : "在线"}
        </span>
      </div>

      <div className="chat-body">
        {hasResult ? (
          <div className="result-chat-content">
            {lastUserMessage ? <div className="result-question">{lastUserMessage.content}</div> : null}
            <article className="answer-card">
              <div className="markdown-body">
                <Markdown>{lastAssistantMessage?.content ?? "结构数据已生成，可在中间区域查看可视化结果，并在右侧核对执行轨迹与数据来源。"}</Markdown>
              </div>
            </article>
          </div>
        ) : messages.length === 0 ? (
          <div className="assistant-intro">
            <div className="assistant-visual" aria-hidden="true">
              <span className="orbit" />
              <span className="halo" />
              <span className="message-orb">
                <MessageCircleMore size={62} />
              </span>
              <i className="star star-1" />
              <i className="star star-2" />
              <i className="star star-3" />
              <i className="star star-4" />
              <i className="star star-5" />
            </div>
            <div className="assistant-copy">
              <strong>你好！我是材料分析助手</strong>
              <p>我可以帮你分析材料结构、性能与工艺</p>
              <p>提出你的问题，开启智能分析吧</p>
            </div>
          </div>
        ) : (
          <div className="message-list">
            {messages.map((message) => (
              <article key={message.id} className={`message ${message.role}${message.streaming ? " streaming" : ""}`}>
                <div className="message-role">{message.role === "user" ? "你" : "材料分析助手"}</div>
                {message.role === "assistant" ? (
                  <div className="markdown-body"><Markdown>{message.content}</Markdown></div>
                ) : (
                  <p>{message.content}</p>
                )}
              </article>
            ))}
          </div>
        )}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <div className="input-shell">
          <span className="input-spark" aria-hidden="true">
            <Sparkles size={18} />
          </span>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="输入材料相关问题，如：LiFePO4 的晶体结构..."
            disabled={running}
          />
          <button type="submit" disabled={running || !draft.trim()} aria-label="发送">
            <SendHorizontal size={21} />
          </button>
        </div>
      </form>
    </section>
  );
}
