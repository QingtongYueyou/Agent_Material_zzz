const state = {
  capabilities: [],
  artifacts: [],
  requestPayload: null,
  responsePayload: null,
};

const elements = {
  connectionCard: document.querySelector("#connectionCard"),
  connectionLabel: document.querySelector("#connectionLabel"),
  upstreamAddress: document.querySelector("#upstreamAddress"),
  capabilityCount: document.querySelector("#capabilityCount"),
  queryInput: document.querySelector("#queryInput"),
  sourceFile: document.querySelector("#sourceFile"),
  fileLabel: document.querySelector("#fileLabel"),
  providerValue: document.querySelector("#providerValue"),
  toolValue: document.querySelector("#toolValue"),
  dispatchButton: document.querySelector("#dispatchButton"),
  artifactTabs: document.querySelector("#artifactTabs"),
  viewerFrame: document.querySelector("#viewerFrame"),
  resultViewer: document.querySelector("#resultViewer"),
  openViewer: document.querySelector("#openViewer"),
  assistantAnswer: document.querySelector("#assistantAnswer"),
  timeline: document.querySelector("#timeline"),
  payloadOutput: document.querySelector("#payloadOutput"),
  toast: document.querySelector("#toast"),
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`${url} 返回了非 JSON 响应`);
  }
  if (!response.ok) {
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return payload;
}

function redact(payload) {
  if (Array.isArray(payload)) return payload.map(redact);
  if (!payload || typeof payload !== "object") return payload;
  return Object.fromEntries(Object.entries(payload).map(([key, value]) => {
    if ((key === "render_url" || key === "model_url") && typeof value === "string") {
      return [key, value.replace(/([?&](?:token|render_id)=)[^&]+/gi, "$1***")];
    }
    return [key, redact(value)];
  }));
}

function setPayload(kind) {
  document.querySelectorAll("[data-payload]").forEach((button) => {
    button.classList.toggle("active", button.dataset.payload === kind);
  });
  const payload = kind === "request" ? state.requestPayload : state.responsePayload;
  elements.payloadOutput.textContent = payload
    ? JSON.stringify(redact(payload), null, 2)
    : `// ${kind} payload will appear here`;
}

function setTimeline(items) {
  elements.timeline.innerHTML = items.map((item) => `
    <li class="${item.status}">
      <span></span>
      <p>${escapeHtml(item.label)}</p>
      <time>${escapeHtml(item.time || "--")}</time>
    </li>
  `).join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  window.setTimeout(() => elements.toast.classList.remove("visible"), 4200);
}

async function initialize() {
  try {
    const [health, catalog] = await Promise.all([
      fetchJson("/api/upstream/health"),
      fetchJson("/api/capabilities"),
    ]);
    elements.connectionCard.classList.add("online");
    elements.connectionLabel.textContent = "Agent Material API 已连接";
    elements.upstreamAddress.textContent = health.upstream_base_url;
    state.capabilities = catalog.capabilities || [];
    elements.capabilityCount.textContent = String(state.capabilities.length).padStart(2, "0");
  } catch (error) {
    elements.connectionCard.classList.add("error");
    elements.connectionLabel.textContent = "上游 API 连接失败";
    elements.dispatchButton.disabled = true;
    showToast(error.message);
  }
}

function resetResult() {
  state.artifacts = [];
  state.responsePayload = null;
  elements.viewerFrame.classList.remove("has-result");
  elements.resultViewer.removeAttribute("src");
  elements.openViewer.classList.add("disabled");
  elements.openViewer.removeAttribute("href");
  elements.artifactTabs.innerHTML = "";
  elements.assistantAnswer.textContent = "";
  elements.providerValue.textContent = "LLM 正在识别意图";
  elements.toolValue.textContent = "tool: planning...";
}

function toolLabel(step) {
  const labels = {
    function_calling: "LLM 意图识别与工具规划",
    file_understanding: "理解上传文件",
    get_mp_structure: "查询 Materials Project 结构",
    search_materials_by_criteria: "检索材料候选",
    inspect_uploaded_file: "深入检查文件内容",
    render_with_mcp: "LLM 调用 MCP 可视化工具",
    visualization_generation: "准备可视化上下文",
    answer_composition: "组织最终回答",
  };
  return labels[step] || step || "Agent step";
}

function answerSummary(answer) {
  const text = String(answer || "Agent 已完成任务。")
    .replace(/[#*_`>|~-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text.length > 260 ? `${text.slice(0, 260)}…` : text;
}

function executionTimeline(events, initialItems) {
  const items = [...initialItems];
  for (const event of events || []) {
    if (event.type !== "step_end") continue;
    const status = event.status === "success" ? "done" : event.status === "failed" ? "error" : "idle";
    items.push({
      label: toolLabel(event.step),
      status,
      time: typeof event.latency_ms === "number" ? `${Math.round(event.latency_ms)} ms` : "--",
    });
  }
  return items;
}

function capabilityForArtifact(artifact) {
  return state.capabilities.find((item) => item.intent === artifact.intent) || null;
}

function displayArtifact(index) {
  const artifact = state.artifacts[index];
  if (!artifact?.render_url) return;
  document.querySelectorAll("#artifactTabs button").forEach((button, buttonIndex) => {
    button.classList.toggle("active", buttonIndex === index);
  });
  const capability = capabilityForArtifact(artifact);
  const provider = artifact.provider || capability?.provider || "MCP provider";
  const tool = artifact.tool || capability?.tool || artifact.intent;
  elements.providerValue.textContent = provider;
  elements.toolValue.textContent = `tool: ${tool}`;
  elements.resultViewer.src = artifact.render_url;
  elements.openViewer.href = artifact.render_url;
  elements.openViewer.classList.remove("disabled");
  elements.viewerFrame.classList.add("has-result");
}

function renderArtifacts(artifacts) {
  state.artifacts = artifacts.filter((item) => item?.render_url);
  elements.artifactTabs.innerHTML = state.artifacts.map((artifact, index) => `
    <button type="button" data-artifact-index="${index}">${escapeHtml(artifact.title || artifact.intent || `结果 ${index + 1}`)}</button>
  `).join("");
  document.querySelectorAll("[data-artifact-index]").forEach((button) => {
    button.addEventListener("click", () => displayArtifact(Number(button.dataset.artifactIndex)));
  });
  if (state.artifacts.length) displayArtifact(0);
}

async function dispatch() {
  const query = elements.queryInput.value.trim();
  if (!query) {
    showToast("请先用自然语言描述需要完成的可视化任务");
    elements.queryInput.focus();
    return;
  }

  const started = performance.now();
  const initialSteps = [];
  const elapsed = () => `${Math.round(performance.now() - started)} ms`;
  resetResult();
  elements.dispatchButton.disabled = true;
  elements.dispatchButton.classList.add("loading");

  try {
    const fileIds = [];
    const file = elements.sourceFile.files[0];
    if (file) {
      setTimeline([{ label: `POST /api/files/upload · ${file.name}`, status: "active", time: "--" }]);
      const form = new FormData();
      form.append("file", file);
      const upload = await fetchJson("/api/files/upload", { method: "POST", body: form });
      fileIds.push(upload.file_id);
      initialSteps.push({ label: `上传文件 · ${upload.filename}`, status: "done", time: elapsed() });
    }

    const request = { query, file_ids: fileIds };
    state.requestPayload = {
      endpoint: "POST /api/chat",
      body: request,
      attachment: file ? { name: file.name, size_bytes: file.size } : null,
    };
    setPayload("request");
    setTimeline([...initialSteps, { label: "POST /api/chat · LLM 自动规划", status: "active", time: elapsed() }]);

    const result = await fetchJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const final = result.final || {};
    state.responsePayload = {
      trace_id: final.trace_id,
      answer: answerSummary(final.answer),
      artifacts: final.artifacts || [],
      step_results: final.step_results || [],
    };
    setPayload("response");
    elements.assistantAnswer.textContent = answerSummary(final.answer);

    const timeline = executionTimeline(result.events, initialSteps);
    timeline.push({ label: "LLM 返回最终结果", status: "done", time: elapsed() });
    setTimeline(timeline);
    renderArtifacts(final.artifacts || []);

    if (!state.artifacts.length) {
      elements.providerValue.textContent = "未产生可视化 Artifact";
      elements.toolValue.textContent = "请在指令中明确要求可视化";
      showToast(final.answer || "LLM 没有调用 MCP 可视化工具");
    }
  } catch (error) {
    setTimeline([{ label: error.message, status: "error", time: elapsed() }]);
    elements.providerValue.textContent = "Agent 执行失败";
    elements.toolValue.textContent = `error: ${error.message}`;
    showToast(error.message);
  } finally {
    elements.dispatchButton.disabled = false;
    elements.dispatchButton.classList.remove("loading");
  }
}

elements.sourceFile.addEventListener("change", () => {
  elements.fileLabel.textContent = elements.sourceFile.files[0]?.name || "添加上下文文件";
});
elements.dispatchButton.addEventListener("click", dispatch);
elements.queryInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") dispatch();
});
document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.queryInput.value = button.dataset.example;
    elements.queryInput.focus();
  });
});
document.querySelectorAll("[data-payload]").forEach((button) => {
  button.addEventListener("click", () => setPayload(button.dataset.payload));
});

initialize();
