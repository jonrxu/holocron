const state = {
  papers: [],
  selectedPaperId: null,
};

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function formatList(items) {
  return items && items.length ? items.join(", ") : "None";
}

function statusLabel(status) {
  return status.replaceAll("_", " ");
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderPapers() {
  const list = document.querySelector("#paper-list");
  list.innerHTML = "";
  for (const paper of state.papers) {
    const li = document.createElement("li");
    const active = paper.id === state.selectedPaperId ? " active" : "";
    li.className = `paper-item${active}`;
    li.innerHTML = `
      <button type="button" data-paper-id="${paper.id}">
        <span class="paper-title">${escapeHtml(paper.title || paper.original_filename || "Untitled paper")}</span>
        <span class="paper-subtitle">${escapeHtml(statusLabel(paper.status))}</span>
        <span class="paper-summary">${escapeHtml(paper.summary_short || "Waiting for analysis...")}</span>
      </button>
    `;
    list.appendChild(li);
  }
}

function renderReviewQueue(items) {
  const list = document.querySelector("#review-queue");
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = `<li class="muted">No review items yet.</li>`;
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.className = "review-item";
    li.innerHTML = `
      <button type="button" data-paper-id="${item.paper_id}">
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(item.reasons.join(" "))}</span>
      </button>
    `;
    list.appendChild(li);
  }
}

function renderDetail(paper) {
  document.querySelector("#empty-state").classList.add("hidden");
  document.querySelector("#paper-detail").classList.remove("hidden");
  document.querySelector("#paper-status").textContent = statusLabel(paper.status);
  document.querySelector("#paper-title").textContent = paper.title || paper.original_filename || "Untitled paper";

  const meta = [];
  if (paper.authors.length) meta.push(paper.authors.join(", "));
  if (paper.year) meta.push(String(paper.year));
  if (paper.source_type) meta.push(`source: ${paper.source_type}`);
  document.querySelector("#paper-meta").textContent = meta.join(" • ");
  document.querySelector("#paper-file-link").href = paper.file_url;
  document.querySelector("#summary-short").textContent = paper.summary_short || "Waiting for analysis...";
  document.querySelector("#summary-long").textContent = paper.summary_long || "";
  document.querySelector("#why-it-matters").textContent = paper.why_it_matters || "Pending analysis.";
  document.querySelector("#method-summary").textContent = paper.method_summary || "Pending analysis.";
  document.querySelector("#tasks").textContent = formatList(paper.tasks);
  document.querySelector("#datasets").textContent = formatList(paper.datasets);
  document.querySelector("#tags").textContent = formatList(paper.tags);
  document.querySelector("#confidence").textContent =
    paper.analysis_confidence != null ? `${Math.round(paper.analysis_confidence * 100)}%` : "Unknown";
  document.querySelector("#note-count").textContent = `${paper.note_count} notes`;

  const fillList = (selector, items) => {
    const list = document.querySelector(selector);
    list.innerHTML = "";
    if (!items || !items.length) {
      list.innerHTML = `<li class="muted">None yet.</li>`;
      return;
    }
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    }
  };

  fillList("#claims", paper.claims);
  fillList("#limitations", paper.limitations);
  fillList("#followups", paper.followup_questions);

  const notes = document.querySelector("#notes");
  notes.innerHTML = "";
  if (!paper.notes.length) {
    notes.innerHTML = `<li class="muted">No notes yet.</li>`;
  } else {
    for (const note of paper.notes) {
      const li = document.createElement("li");
      li.className = "note-item";
      const page = note.page_number ? ` • p.${note.page_number}` : "";
      li.innerHTML = `<p>${escapeHtml(note.body)}</p><span class="muted">${escapeHtml(note.created_at)}${page}</span>`;
      notes.appendChild(li);
    }
  }

  const events = document.querySelector("#events");
  events.innerHTML = "";
  for (const event of paper.events) {
    const li = document.createElement("li");
    li.className = "event-item";
    li.innerHTML = `
      <strong>${escapeHtml(event.event_type.replaceAll("_", " "))}</strong>
      <span class="muted">${escapeHtml(event.created_at)}</span>
    `;
    events.appendChild(li);
  }
}

async function loadPapers(selectedPaperId = state.selectedPaperId) {
  const [{ papers }, { items }] = await Promise.all([
    request("/api/papers"),
    request("/api/review-queue"),
  ]);
  state.papers = papers;
  renderPapers();
  renderReviewQueue(items);

  const paperToLoad =
    selectedPaperId ||
    state.selectedPaperId ||
    (state.papers.length ? state.papers[0].id : null);

  if (paperToLoad) {
    await loadPaper(paperToLoad);
  }
}

async function loadPaper(paperId) {
  state.selectedPaperId = paperId;
  renderPapers();
  const { paper } = await request(`/api/papers/${paperId}`);
  renderDetail(paper);
  await request(`/api/papers/${paperId}/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}

function bindEvents() {
  document.querySelector("#paper-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-paper-id]");
    if (!button) return;
    await loadPaper(Number(button.dataset.paperId));
  });

  document.querySelector("#review-queue").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-paper-id]");
    if (!button) return;
    await loadPaper(Number(button.dataset.paperId));
  });

  document.querySelector("#refresh-button").addEventListener("click", async () => {
    await loadPapers();
  });

  document.querySelector("#upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.querySelector("#upload-status");
    const input = document.querySelector("#paper-file");
    if (!input.files.length) return;
    status.textContent = "Uploading...";
    const formData = new FormData();
    formData.append("file", input.files[0]);
    try {
      const { paper } = await request("/api/papers/upload", {
        method: "POST",
        body: formData,
      });
      status.textContent = paper.duplicate ? "Duplicate detected. Existing paper opened." : "Paper queued for analysis.";
      input.value = "";
      await loadPapers(paper.id);
    } catch (error) {
      status.textContent = error.message;
    }
  });

  document.querySelector("#url-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.querySelector("#upload-status");
    const input = document.querySelector("#paper-url");
    if (!input.value.trim()) return;
    status.textContent = "Downloading...";
    try {
      const { paper } = await request("/api/papers/from-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: input.value.trim() }),
      });
      status.textContent = "Paper queued for analysis.";
      input.value = "";
      await loadPapers(paper.id);
    } catch (error) {
      status.textContent = error.message;
    }
  });

  document.querySelector("#note-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.selectedPaperId) return;
    const body = document.querySelector("#note-body").value.trim();
    if (!body) return;
    const pageValue = document.querySelector("#note-page").value;
    const { paper } = await request(`/api/papers/${state.selectedPaperId}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        body,
        page_number: pageValue ? Number(pageValue) : null,
      }),
    });
    document.querySelector("#note-body").value = "";
    document.querySelector("#note-page").value = "";
    renderDetail(paper);
    await loadPapers(state.selectedPaperId);
  });

  document.querySelector("#important-button").addEventListener("click", async () => {
    if (!state.selectedPaperId) return;
    const { paper } = await request(`/api/papers/${state.selectedPaperId}/tags/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag: "status:important" }),
    });
    renderDetail(paper);
    await loadPapers(state.selectedPaperId);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadPapers();
});
