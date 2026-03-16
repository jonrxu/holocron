const state = {
  allPapers: [],
  libraryPapers: [],
  libraryGraph: { nodes: [] },
  selectedPaperId: null,
  searchQuery: "",
};

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

let searchTimer = null;

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

function truncate(value, maxLength = 180) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

function statusLabel(status) {
  return String(status || "").replaceAll("_", " ");
}

function buildLibraryUrl() {
  const params = new URLSearchParams();
  if (state.searchQuery.trim()) {
    params.set("q", state.searchQuery.trim());
  }
  return params.toString() ? `/api/papers?${params.toString()}` : "/api/papers";
}

function renderHeader() {
  const total = state.allPapers.length;
  const shown = state.libraryPapers.length;
  document.querySelector("#library-meta").textContent =
    state.searchQuery.trim() ? `${shown} of ${total} papers` : `${total} papers`;
  document.querySelector("#library-count").textContent = `${shown} shown`;
  document.querySelector("#library-graph-count").textContent = `${state.libraryGraph.nodes.length} points`;
}

function renderPaperList() {
  const list = document.querySelector("#paper-list");
  list.innerHTML = "";

  if (!state.libraryPapers.length) {
    list.innerHTML = `<li class="empty-list">No papers match this search.</li>`;
    return;
  }

  for (const paper of state.libraryPapers) {
    const li = document.createElement("li");
    li.className = paper.id === state.selectedPaperId ? "paper-row active" : "paper-row";

    const meta = [statusLabel(paper.status), formatDate(paper.added_at)];
    if (paper.semantic_score > 0 && state.searchQuery.trim()) {
      meta.unshift(`match ${Math.round(paper.semantic_score * 100)}%`);
    }

    li.innerHTML = `
      <button type="button" class="paper-button" data-paper-id="${paper.id}">
        <span class="paper-title">${escapeHtml(paper.title || paper.original_filename || "Untitled paper")}</span>
        <span class="paper-meta">${escapeHtml(meta.join(" • "))}</span>
        <span class="paper-summary">${escapeHtml(truncate(paper.summary_short || "Waiting for analysis..."))}</span>
      </button>
    `;
    list.appendChild(li);
  }
}

function renderTags(tags) {
  const list = document.querySelector("#paper-tags");
  list.innerHTML = "";

  if (!tags || !tags.length) {
    list.innerHTML = `<li class="empty-list">Tags will appear after analysis.</li>`;
    return;
  }

  for (const tag of tags.slice(0, 8)) {
    const li = document.createElement("li");
    li.className = "signal-chip";
    li.textContent = tag;
    list.appendChild(li);
  }
}

function renderNotes(notes) {
  const list = document.querySelector("#notes");
  list.innerHTML = "";

  if (!notes.length) {
    list.innerHTML = `<li class="empty-list">No notes yet.</li>`;
    return;
  }

  for (const note of notes) {
    const li = document.createElement("li");
    const page = note.page_number ? ` • p.${note.page_number}` : "";
    li.innerHTML = `
      <p>${escapeHtml(note.body)}</p>
      <time>${escapeHtml(formatDate(note.created_at))}${page}</time>
    `;
    list.appendChild(li);
  }
}

function renderDetail(paper) {
  document.querySelector("#empty-detail").classList.add("hidden");
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
  document.querySelector("#summary-short").textContent = paper.summary_short || "Waiting for analysis...";
  document.querySelector("#paper-file-link").href = paper.file_url;
  document.querySelector("#note-count").textContent = `${paper.note_count} notes`;

  renderTags(paper.tags || []);
  renderNotes(paper.notes || []);
}

function selectEmptyState() {
  document.querySelector("#paper-detail").classList.add("hidden");
  document.querySelector("#empty-detail").classList.remove("hidden");
}

function renderMap() {
  const viewport = document.querySelector("#library-map-viewport");
  viewport.innerHTML = "";
  document.querySelector("#map-empty").classList.toggle("hidden", state.libraryGraph.nodes.length > 0);

  for (const node of state.libraryGraph.nodes) {
    const x = 50 + node.x * 38;
    const y = 50 + node.y * 38;
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("transform", `translate(${x} ${y})`);
    group.setAttribute("data-paper-id", String(node.id));
    group.setAttribute("class", node.id === state.selectedPaperId ? "map-node selected" : "map-node");

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", node.id === state.selectedPaperId ? "1.9" : "1.35");
    circle.setAttribute("class", "map-dot");
    group.appendChild(circle);

    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = node.title || "Untitled paper";
    group.appendChild(title);

    if (node.id === state.selectedPaperId) {
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("y", "-3.2");
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("class", "map-label");
      label.textContent = node.title || "Untitled paper";
      group.appendChild(label);
    }

    viewport.appendChild(group);
  }
}

async function loadPaper(paperId) {
  state.selectedPaperId = paperId;
  renderPaperList();
  renderMap();
  const { paper } = await request(`/api/papers/${paperId}`);
  renderDetail(paper);
}

async function loadPapers(selectedPaperId = state.selectedPaperId, options = {}) {
  const libraryUrl = buildLibraryUrl();
  const requests = [request(libraryUrl)];
  if (libraryUrl === "/api/papers") {
    requests.push(Promise.resolve(null));
  } else {
    requests.push(request("/api/papers"));
  }

  const [libraryPayload, allPayload] = await Promise.all(requests);
  state.libraryPapers = libraryPayload.papers;
  state.libraryGraph = libraryPayload.graph || { nodes: [] };
  state.allPapers = (allPayload || libraryPayload).papers;

  const stillVisible = selectedPaperId != null && state.libraryPapers.some((paper) => paper.id === selectedPaperId);
  const shouldAutoSelect = !stillVisible && options.autoSelectFirst && state.libraryPapers.length > 0;

  if (stillVisible) {
    state.selectedPaperId = selectedPaperId;
  } else if (shouldAutoSelect) {
    state.selectedPaperId = state.libraryPapers[0].id;
  } else {
    state.selectedPaperId = null;
  }

  renderHeader();
  renderPaperList();
  renderMap();

  if (state.selectedPaperId != null) {
    await loadPaper(state.selectedPaperId);
  } else {
    selectEmptyState();
  }
}

async function handleUpload(file) {
  const status = document.querySelector("#upload-status");
  if (!file) {
    return;
  }

  status.textContent = "Uploading...";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const { paper } = await request("/api/papers/upload", {
      method: "POST",
      body: formData,
    });
    status.textContent = paper.duplicate ? "Already in the library." : "Paper queued for analysis.";
    state.searchQuery = "";
    document.querySelector("#library-search").value = "";
    await loadPapers(paper.id, { autoSelectFirst: false });
    await loadPaper(paper.id);
  } catch (error) {
    status.textContent = error.message;
  }
}

function bindSearch() {
  const input = document.querySelector("#library-search");
  input.addEventListener("input", (event) => {
    state.searchQuery = event.target.value;
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(async () => {
      await loadPapers(state.selectedPaperId, { autoSelectFirst: Boolean(state.searchQuery.trim()) });
    }, 220);
  });
}

function bindUpload() {
  const input = document.querySelector("#paper-file");
  const drop = document.querySelector("#upload-drop");

  input.addEventListener("change", async (event) => {
    const [file] = event.target.files;
    await handleUpload(file);
    input.value = "";
  });

  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("dragging");
  });

  drop.addEventListener("dragleave", () => {
    drop.classList.remove("dragging");
  });

  drop.addEventListener("drop", async (event) => {
    event.preventDefault();
    drop.classList.remove("dragging");
    const [file] = event.dataTransfer.files;
    await handleUpload(file);
  });
}

function bindSelection() {
  document.querySelector("#paper-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-paper-id]");
    if (!button) {
      return;
    }
    await loadPaper(Number(button.dataset.paperId));
  });

  document.querySelector("#library-map").addEventListener("click", async (event) => {
    const node = event.target.closest("[data-paper-id]");
    if (!node) {
      return;
    }
    await loadPaper(Number(node.dataset.paperId));
  });
}

function bindNotes() {
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
    await loadPapers(state.selectedPaperId, { autoSelectFirst: false });
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  bindSearch();
  bindUpload();
  bindSelection();
  bindNotes();
  await loadPapers(null, { autoSelectFirst: false });
});
