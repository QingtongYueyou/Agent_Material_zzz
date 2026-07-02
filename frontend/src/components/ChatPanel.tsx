import { Dispatch, FormEvent, SetStateAction, useRef, useState } from "react";
import {
  AlertCircle,
  FileText,
  LoaderCircle,
  MessageCircleMore,
  Paperclip,
  SendHorizontal,
  X,
} from "lucide-react";
import Markdown from "react-markdown";
import { uploadFile } from "../api";
import type { ChatMessage, UploadedFile, VizData } from "../types";

interface ChatPanelProps {
  messages: ChatMessage[];
  running: boolean;
  viz: VizData | null;
  attachments: UploadedFile[];
  onAttachmentsChange: Dispatch<SetStateAction<UploadedFile[]>>;
  onSubmit: (query: string, fileIds: string[]) => void;
}

interface ParsedAssistantContent {
  answer: string;
  thoughts: string[];
}

export function ChatPanel({
  messages,
  running,
  viz,
  attachments,
  onAttachmentsChange,
  onSubmit,
}: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
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
    setUploadError("");
    onSubmit(value, attachments.map((file) => file.file_id));
  }

  async function handleFilesSelected(files: FileList | null) {
    if (!files?.length || running) {
      return;
    }

    setUploading(true);
    setUploadError("");
    const uploaded: UploadedFile[] = [];
    const failures: string[] = [];

    for (const file of Array.from(files)) {
      try {
        uploaded.push(await uploadFile(file));
      } catch (err) {
        const message = err instanceof Error ? err.message : "上传失败";
        failures.push(`${file.name}: ${message}`);
      }
    }

    if (uploaded.length > 0) {
      onAttachmentsChange((current) => [...current, ...uploaded]);
    }
    if (failures.length > 0) {
      setUploadError(failures.join("；"));
    }

    setUploading(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function removeAttachment(fileId: string) {
    onAttachmentsChange((current) => current.filter((file) => file.file_id !== fileId));
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
            <article className={`answer-card${lastAssistantMessage?.streaming ? " streaming" : ""}`}>
              <div className="markdown-body">
                <AssistantContent content={lastAssistantMessage?.content ?? "结构数据已生成，可在中间区域查看可视化结果，并在右侧核对执行轨迹与数据来源。"} />
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
                  <div className="markdown-body"><AssistantContent content={message.content} /></div>
                ) : (
                  <p>{message.content}</p>
                )}
              </article>
            ))}
          </div>
        )}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        {attachments.length > 0 || uploadError ? (
          <div className="attachment-region">
            {attachments.length > 0 ? (
              <div className="attachment-list" aria-label="已上传附件">
                {attachments.map((file) => (
                  <span className="attachment-chip" key={file.file_id} title={file.filename}>
                    <FileText size={14} />
                    <span className="attachment-name">{file.filename}</span>
                    <small>{formatFileSize(file.size_bytes)}</small>
                    <button
                      type="button"
                      onClick={() => removeAttachment(file.file_id)}
                      disabled={running}
                      aria-label={`移除附件 ${file.filename}`}
                    >
                      <X size={13} />
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
            {attachments.length > 0 ? (
              <p className="attachment-note">可视化时文件会发送到远程 MCP 服务进行渲染。</p>
            ) : null}
            {uploadError ? (
              <div className="attachment-error" role="alert">
                <AlertCircle size={14} />
                <span>{uploadError}</span>
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="input-shell">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="file-input"
            onChange={(event) => void handleFilesSelected(event.target.files)}
            disabled={running || uploading}
          />
          <button
            type="button"
            className="attach-button"
            onClick={() => fileInputRef.current?.click()}
            disabled={running || uploading}
            aria-label="上传附件"
            title="上传附件"
          >
            {uploading ? <LoaderCircle size={18} className="spin" /> : <Paperclip size={18} />}
          </button>
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

function formatFileSize(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = sizeBytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`;
}

function AssistantContent({ content }: { content: string }) {
  const { answer, thoughts } = parseAssistantContent(content);

  return (
    <>
      {thoughts.map((thought, index) => (
        <details className="thought-disclosure" key={`${index}-${thought.slice(0, 24)}`}>
          <summary>
            <span>思考过程</span>
            <small>点击展开</small>
          </summary>
          <div className="thought-body">
            <Markdown>{thought}</Markdown>
          </div>
        </details>
      ))}
      {answer.trim() ? <Markdown>{answer}</Markdown> : null}
    </>
  );
}

function parseAssistantContent(content: string): ParsedAssistantContent {
  const thoughts: string[] = [];
  let answer = "";
  let cursor = 0;
  const thinkBlockPattern = /<think>([\s\S]*?)(?:<\/think>|$)/gi;
  let match: RegExpExecArray | null;

  while ((match = thinkBlockPattern.exec(content)) !== null) {
    answer += content.slice(cursor, match.index);
    thoughts.push(match[1].trim());
    cursor = match.index + match[0].length;
  }

  answer += content.slice(cursor);

  return {
    answer: answer.trim(),
    thoughts: thoughts.filter(Boolean)
  };
}
