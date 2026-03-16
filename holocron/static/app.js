const state = {
  activeView: "home",
  papers: [],
  reviewQueue: [],
  selectedPaperId: null,
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

function formatList(items) {
  return items && items.length ? items.join(", ") : "None";
}

function statusLabel(status) {
  return String(status || "").replaceAll("_", " ");
}

function formatDate(value) {
  if (!value) {
    return "Nothing yet";
  }
  return dateFormatter.format(new Date(value));
}

function setView(view) {
  state.activeView = view;
  document.querySelector("#view-home").classList.toggle("hidden", view !== "home");
  document.querySelector("#view-library").classList.toggle("hidden", view !== "library");
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
}

function renderReviewQueue() {
  const list = document.querySelector("#review-queue");
  list.innerHTML = "";
  if (!state.reviewQueue.length) {
    list.innerHTML = `<li class="empty-list">Nothing needs attention right now.</li>`;
    return;
  }

  for (const item of state.reviewQueue.slice(0, 6)) {
    const li = document.createElement("li");
    li.className = "review-item";
    li.innerHTML = `
      <button type="button" data-paper-id="${item.paper_id}">
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.reasons[0])}</p>
      </button>
    `;
    list.appendChild(li);
  }
}

function renderHome() {
  document.querySelector("#metric-papers").textContent = state.papers.length;
  document.querySelector("#metric-review").textContent = state.reviewQueue.length;
  document.querySelector("#metric-latest").textContent = state.papers.length
    ? formatDate(state.papers[0].added_at)
    : "Nothing yet";

  const list = document.querySelector("#recent-papers");
  list.innerHTML = "";
  if (!state.papers.length) {
    list.innerHTML = `<li class="empty-list">Your uploads will appear here.</li>`;
    return;
  }

  for (const paper of state.papers.slice(0, 5)) {
    const li = document.createElement("li");
    li.className = "recent-paper";
    li.innerHTML = `
      <button type="button" data-paper-id="${paper.id}">
        <span class="paper-title">${escapeHtml(paper.title || paper.original_filename || "Untitled paper")}</span>
        <span class="paper-meta">${escapeHtml(formatDate(paper.added_at))} • ${escapeHtml(statusLabel(paper.status))}</span>
      </button>
    `;
    list.appendChild(li);
  }
}

function renderLibraryList() {
  const list = document.querySelector("#paper-list");
  list.innerHTML = "";
  if (!state.papers.length) {
    list.innerHTML = `<li class="empty-list">No papers yet.</li>`;
    return;
  }

  for (const paper of state.papers) {
    const li = document.createElement("li");
    const active = paper.id === state.selectedPaperId ? " active" : "";
    li.className = `paper-card${active}`;
    li.innerHTML = `
      <button type="button" data-paper-id="${paper.id}">
        <span class="paper-title">${escapeHtml(paper.title || paper.original_filename || "Untitled paper")}</span>
        <span class="paper-meta">${escapeHtml(statusLabel(paper.status))}</span>
        <span class="paper-meta">${escapeHtml(paper.summary_short || "Waiting for analysis...")}</span>
      </button>
    `;
    list.appendChild(li);
  }
}

function fillList(selector, items, emptyMessage = "None yet.") {
  const list = document.querySelector(selector);
  list.innerHTML = "";
  if (!items || !items.length) {
    list.innerHTML = `<li class="empty-list">${escapeHtml(emptyMessage)}</li>`;
    return;
  }

  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  }
}

function renderConstellation(paper) {
  document.querySelector("#constellation-core").textContent = paper.title || "Untitled paper";
  const cloud = document.querySelector("#constellation-chips");
  cloud.innerHTML = "";
  const chips = [...paper.tags, ...paper.tasks, ...paper.datasets].slice(0, 12);

  if (!chips.length) {
    cloud.innerHTML = `<span>Signals will appear after analysis.</span>`;
    return;
  }

  for (const item of chips) {
    const chip = document.createElement("span");
    chip.textContent = item;
    cloud.appendChild(chip);
  }
}

function renderNotes(paper) {
  const notes = document.querySelector("#notes");
  notes.innerHTML = "";
  if (!paper.notes.length) {
    notes.innerHTML = `<li class="empty-list">No notes yet.</li>`;
    return;
  }

  for (const note of paper.notes) {
    const li = document.createElement("li");
    const page = note.page_number ? ` • p.${note.page_number}` : "";
    li.innerHTML = `
      <p>${escapeHtml(note.body)}</p>
      <time>${escapeHtml(formatDate(note.created_at))}${page}</time>
    `;
    notes.appendChild(li);
  }
}

function renderEvents(paper) {
  const events = document.querySelector("#events");
  events.innerHTML = "";
  if (!paper.events.length) {
    events.innerHTML = `<li class="empty-list">No activity yet.</li>`;
    return;
  }

  for (const event of paper.events) {
    const li = document.createElement("li");
    li.innerHTML = `
      <p>${escapeHtml(event.event_type.replaceAll("_", " "))}</p>
      <time>${escapeHtml(formatDate(event.created_at))}</time>
    `;
    events.appendChild(li);
  }
}

function renderDetail(paper) {
  document.querySelector("#empty-state").classList.add("hidden");
  document.querySelector("#paper-detail").classList.remove("hidden");
  document.querySelector("#paper-status").textContent = statusLabel(paper.status);
  document.querySelector("#paper-title").textContent = paper.title || paper.original_filename || "Untitled paper";

  const meta = [];
  if (paper.authors.length) {
    meta.push(paper.authors.join(", "));
  }
  if (paper.year) {
    meta.push(String(paper.year));
  }
  meta.push(`added ${formatDate(paper.added_at)}`);
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

  const importantButton = document.querySelector("#important-button");
  const important = paper.tags.includes("status:important");
  importantButton.textContent = important ? "Unmark important" : "Mark important";

  fillList("#claims", paper.claims, "No claims extracted yet.");
  fillList("#limitations", paper.limitations, "No limitations extracted yet.");
  fillList("#followups", paper.followup_questions, "No follow-up questions yet.");
  renderConstellation(paper);
  renderNotes(paper);
  renderEvents(paper);
}

async function loadPaper(paperId, options = {}) {
  state.selectedPaperId = paperId;
  renderLibraryList();
  const { paper } = await request(`/api/papers/${paperId}`);
  renderDetail(paper);
  if (options.switchView !== false) {
    setView("library");
  }
  await request(`/api/papers/${paperId}/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}

async function loadPapers(selectedPaperId = state.selectedPaperId) {
  const [{ papers }, { items }] = await Promise.all([
    request("/api/papers"),
    request("/api/review-queue"),
  ]);

  state.papers = papers;
  state.reviewQueue = items;
  renderReviewQueue();
  renderHome();
  renderLibraryList();

  if (!state.papers.length) {
    document.querySelector("#empty-state").classList.remove("hidden");
    document.querySelector("#paper-detail").classList.add("hidden");
    state.selectedPaperId = null;
    return;
  }

  const nextPaperId =
    selectedPaperId && state.papers.some((paper) => paper.id === selectedPaperId)
      ? selectedPaperId
      : state.selectedPaperId && state.papers.some((paper) => paper.id === state.selectedPaperId)
        ? state.selectedPaperId
        : state.papers[0].id;

  if (nextPaperId) {
    await loadPaper(nextPaperId, { switchView: false });
  }
}

function bindNavigation() {
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.addEventListener("click", async () => {
      const view = button.dataset.view;
      setView(view);
      if (view === "library" && state.papers.length && state.selectedPaperId == null) {
        await loadPaper(state.papers[0].id, { switchView: false });
      }
    });
  });

  document.querySelector("#go-library-button").addEventListener("click", async () => {
    setView("library");
    if (state.papers.length) {
      await loadPaper(state.selectedPaperId || state.papers[0].id, { switchView: false });
    }
  });
}

function bindPaperSelection() {
  const selectPaper = async (event) => {
    const button = event.target.closest("button[data-paper-id]");
    if (!button) {
      return;
    }
    await loadPaper(Number(button.dataset.paperId));
  };

  document.querySelector("#recent-papers").addEventListener("click", selectPaper);
  document.querySelector("#paper-list").addEventListener("click", selectPaper);
  document.querySelector("#review-queue").addEventListener("click", selectPaper);
}

function bindUploadForms() {
  document.querySelector("#upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.querySelector("#upload-status");
    const input = document.querySelector("#paper-file");
    if (!input.files.length) {
      return;
    }

    status.textContent = "Uploading...";
    const formData = new FormData();
    formData.append("file", input.files[0]);

    try {
      const { paper } = await request("/api/papers/upload", {
        method: "POST",
        body: formData,
      });
      status.textContent = paper.duplicate ? "Already in the library. Opening it now." : "Paper queued for analysis.";
      input.value = "";
      setView("library");
      await loadPapers(paper.id);
    } catch (error) {
      status.textContent = error.message;
    }
  });

  document.querySelector("#url-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.querySelector("#upload-status");
    const input = document.querySelector("#paper-url");
    const url = input.value.trim();
    if (!url) {
      return;
    }

    status.textContent = "Downloading...";
    try {
      const { paper } = await request("/api/papers/from-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      status.textContent = "Paper queued for analysis.";
      input.value = "";
      setView("library");
      await loadPapers(paper.id);
    } catch (error) {
      status.textContent = error.message;
    }
  });
}

function bindDetailActions() {
  document.querySelector("#note-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.selectedPaperId) {
      return;
    }

    const bodyInput = document.querySelector("#note-body");
    const pageInput = document.querySelector("#note-page");
    const body = bodyInput.value.trim();
    if (!body) {
      return;
    }

    const { paper } = await request(`/api/papers/${state.selectedPaperId}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        body,
        page_number: pageInput.value ? Number(pageInput.value) : null,
      }),
    });

    bodyInput.value = "";
    pageInput.value = "";
    renderDetail(paper);
    await loadPapers(state.selectedPaperId);
  });

  document.querySelector("#important-button").addEventListener("click", async () => {
    if (!state.selectedPaperId) {
      return;
    }

    const { paper } = await request(`/api/papers/${state.selectedPaperId}/tags/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag: "status:important" }),
    });

    renderDetail(paper);
    await loadPapers(state.selectedPaperId);
  });

  document.querySelector("#refresh-button").addEventListener("click", async () => {
    await loadPapers();
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  bindNavigation();
  bindPaperSelection();
  bindUploadForms();
  bindDetailActions();
  setView("home");
  await loadPapers();
});
