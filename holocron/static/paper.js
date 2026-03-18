const state = {
  paperId: null,
  paper: null,
  chatMessages: [],
  activeCitation: null,
  pollTimer: null,
};

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatDate(value) {
  if (!value) {
    return "Nothing yet";
  }
  return dateFormatter.format(new Date(value));
}

function truncate(value, maxLength = 260) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

function statusLabel(status) {
  return String(status || "").replaceAll("_", " ");
}

function toAbsoluteUrl(path) {
  return new URL(path, window.location.origin).href;
}

function parsePaperId() {
  const match = window.location.pathname.match(/^\/papers\/(\d+)\/?$/);
  return match ? Number(match[1]) : null;
}

function paperIsProcessing() {
  return !state.paper || ["queued", "processing"].includes(state.paper.status);
}

function ensureIntroMessage() {
  const intro = state.chatMessages.find((message) => message.kind === "system");
  const processing = paperIsProcessing();
  const content = processing
    ? "This paper is still processing. You can start reading the PDF now."
    : "Ask questions about the paper while you read.";

  if (intro) {
    intro.body = content;
    return;
  }

  state.chatMessages.unshift({
    id: "system-intro",
    role: "assistant",
    kind: "system",
    body: content,
    citations: [],
    model: "",
  });
}

function renderChat() {
  const thread = document.querySelector("#chat-thread");
  thread.innerHTML = "";

  ensureIntroMessage();

  for (const message of state.chatMessages) {
    const section = document.createElement("section");
    section.className = `chat-message ${message.role}`;
    section.innerHTML = `<p>${escapeHtml(message.body)}</p>`;

    if (message.role === "assistant" && message.model) {
      const meta = document.createElement("p");
      meta.className = "chat-meta";
      meta.textContent = `answered by ${message.model}`;
      section.appendChild(meta);
    }

    if (message.role === "assistant" && message.citations?.length) {
      const sources = document.createElement("div");
      sources.className = "chat-sources";
      for (const [index, citation] of message.citations.entries()) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "citation-chip";
        button.dataset.messageId = message.id;
        button.dataset.citationIndex = String(index);
        button.textContent = `[${citation.chunk_index}]`;
        sources.appendChild(button);

        if (
          state.activeCitation
          && state.activeCitation.messageId === message.id
          && state.activeCitation.citationIndex === index
        ) {
          const popup = document.createElement("div");
          popup.className = "citation-popover";
          popup.innerHTML = `
            <p>${escapeHtml(truncate(citation.snippet, 420))}</p>
            <time>${escapeHtml(`Excerpt ${citation.chunk_index}`)}</time>
          `;
          sources.appendChild(popup);
        }
      }
      section.appendChild(sources);
    }

    thread.appendChild(section);
  }

  thread.scrollTop = thread.scrollHeight;
}

function renderComposer() {
  const input = document.querySelector("#ask-question");
  const submit = document.querySelector("#ask-submit");
  const status = document.querySelector("#ask-status");
  const processing = paperIsProcessing();

  input.disabled = processing;
  submit.disabled = processing;
  input.placeholder = processing
    ? "Questions unlock when processing finishes"
    : "Ask this paper a question";

  if (processing) {
    status.textContent = "Processing paper...";
  } else if (status.textContent === "Processing paper...") {
    status.textContent = "";
  }
}

function renderPaper() {
  if (!state.paper) {
    return;
  }

  document.title = `${state.paper.title || "Holocron"} • Holocron`;
  document.querySelector("#paper-status").textContent = statusLabel(state.paper.status);
  document.querySelector("#chat-meta").textContent = `Added ${formatDate(state.paper.added_at)}`;
  document.querySelector("#paper-file-link").href = state.paper.file_url;

  const frame = document.querySelector("#pdf-frame");
  const pdfUrl = toAbsoluteUrl(state.paper.file_url);
  if (frame.src !== pdfUrl) {
    frame.src = pdfUrl;
  }

  renderComposer();
  ensureIntroMessage();
  renderChat();
}

async function loadPaper() {
  const { paper } = await request(`/api/papers/${state.paperId}`);
  state.paper = paper;
  renderPaper();
  schedulePoll();
}

function schedulePoll() {
  window.clearTimeout(state.pollTimer);
  if (!state.paper || !["queued", "processing"].includes(state.paper.status)) {
    return;
  }
  state.pollTimer = window.setTimeout(async () => {
    await loadPaper();
  }, 2000);
}

async function submitQuestion(event) {
  event.preventDefault();
  if (!state.paperId || paperIsProcessing()) {
    return;
  }

  const input = document.querySelector("#ask-question");
  const submit = document.querySelector("#ask-submit");
  const status = document.querySelector("#ask-status");
  const modelLabel = document.querySelector("#ask-model");
  const question = input.value.trim();
  if (!question) {
    return;
  }

  state.chatMessages.push({
    id: `user-${Date.now()}`,
    role: "user",
    kind: "question",
    body: question,
    citations: [],
    model: "",
  });
  renderChat();

  input.value = "";
  submit.disabled = true;
  status.textContent = "Thinking...";

  try {
    const { answer } = await request(`/api/papers/${state.paperId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    state.chatMessages.push({
      id: `assistant-${Date.now()}`,
      role: "assistant",
      kind: "answer",
      body: answer.answer,
      citations: answer.citations || [],
      model: answer.model || "",
    });
    modelLabel.textContent = answer.model ? `using ${answer.model}` : "";
    status.textContent = "";
    renderChat();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

function bindUi() {
  document.querySelector("#ask-form").addEventListener("submit", submitQuestion);
  renderComposer();
  document.querySelector("#chat-thread").addEventListener("click", (event) => {
    const button = event.target.closest(".citation-chip");
    if (!button) {
      return;
    }
    const messageId = button.dataset.messageId;
    const citationIndex = Number(button.dataset.citationIndex);
    if (
      state.activeCitation
      && state.activeCitation.messageId === messageId
      && state.activeCitation.citationIndex === citationIndex
    ) {
      state.activeCitation = null;
    } else {
      state.activeCitation = { messageId, citationIndex };
    }
    renderChat();
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  state.paperId = parsePaperId();
  bindUi();

  if (!state.paperId) {
    state.chatMessages = [
      {
        id: "missing-paper",
        role: "assistant",
        kind: "system",
        body: "The URL is missing a valid paper id.",
        citations: [],
        model: "",
      },
    ];
    renderChat();
    return;
  }

  try {
    await loadPaper();
  } catch (error) {
    state.chatMessages = [
      {
        id: "paper-error",
        role: "assistant",
        kind: "system",
        body: error.message,
        citations: [],
        model: "",
      },
    ];
    renderChat();
  }
});
