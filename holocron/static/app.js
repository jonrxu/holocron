const state = {
  allPapers: [],
  libraryPapers: [],
  libraryGraph: { nodes: [] },
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

function paperUrl(paperId) {
  return `/papers/${paperId}`;
}

function buildLibraryUrl() {
  const params = new URLSearchParams();
  if (state.searchQuery.trim()) {
    params.set("q", state.searchQuery.trim());
  }
  return params.toString() ? `/api/papers?${params.toString()}` : "/api/papers";
}

async function runSearch() {
  window.clearTimeout(searchTimer);
  await loadPapers();
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
    li.className = "paper-row";

    const meta = [statusLabel(paper.status), formatDate(paper.added_at)];
    if (paper.semantic_score > 0 && state.searchQuery.trim()) {
      meta.unshift(`match ${Math.round(paper.semantic_score * 100)}%`);
    }

    li.innerHTML = `
      <a class="paper-link" href="${paperUrl(paper.id)}" data-paper-id="${paper.id}">
        <span class="paper-title">${escapeHtml(paper.title || paper.original_filename || "Untitled paper")}</span>
        <span class="paper-meta">${escapeHtml(meta.join(" • "))}</span>
        <span class="paper-summary">${escapeHtml(truncate(paper.summary_short || "Waiting for analysis..."))}</span>
      </a>
    `;
    list.appendChild(li);
  }
}

function renderMap() {
  const viewport = document.querySelector("#library-map-viewport");
  viewport.innerHTML = "";
  document.querySelector("#map-empty").classList.toggle("hidden", state.libraryGraph.nodes.length > 0);

  for (const node of state.libraryGraph.nodes) {
    const x = 50 + node.x * 38;
    const y = 50 + node.y * 38;
    const link = document.createElementNS("http://www.w3.org/2000/svg", "a");
    link.setAttribute("href", paperUrl(node.id));
    link.setAttribute("data-paper-id", String(node.id));
    link.setAttribute("class", "map-node");

    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("transform", `translate(${x} ${y})`);

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", "1.4");
    circle.setAttribute("class", "map-dot");
    group.appendChild(circle);

    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = node.title || "Untitled paper";
    group.appendChild(title);

    link.appendChild(group);
    viewport.appendChild(link);
  }
}

async function loadPapers() {
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

  renderHeader();
  renderPaperList();
  renderMap();
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
    window.location.href = paperUrl(paper.id);
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
      await runSearch();
    }, 220);
  });

  input.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    state.searchQuery = input.value;
    await runSearch();
  });

  input.addEventListener("search", async (event) => {
    state.searchQuery = event.target.value;
    await runSearch();
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

document.addEventListener("DOMContentLoaded", async () => {
  bindSearch();
  bindUpload();
  await loadPapers();
});
