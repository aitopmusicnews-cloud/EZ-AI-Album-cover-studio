const terminalStatuses = new Set([
  "complete", "partial", "analysis_failed", "image_failed", "needs_mood_choice"
]);

const state = {
  collectionId: getCollectionId(),
  generation: null,
  busy: false,
  pollToken: 0,
};

const form = document.querySelector("#generation-form");
const submitButton = document.querySelector("#submit-button");
const formError = document.querySelector("#form-error");
const resultRoot = document.querySelector("#result");
const historyRoot = document.querySelector("#history");
document.querySelector("#collection-label").textContent = `Audit collection: ${state.collectionId.slice(0, 12)}…`;

form.addEventListener("submit", submitGeneration);
refreshHistory().catch(() => undefined);

function getCollectionId() {
  const existing = localStorage.getItem("album-cover-collection");
  if (existing) return existing;
  const created = crypto.randomUUID().replaceAll("-", "");
  localStorage.setItem("album-cover-collection", created);
  return created;
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || `Request failed (${response.status})`);
  return body;
}

async function submitGeneration(event) {
  event.preventDefault();
  const audio = document.querySelector("#audio").files[0];
  const lyricsFile = document.querySelector("#lyrics-file").files[0];
  const lyricsText = document.querySelector("#lyrics-text").value.trim();
  const count = Number(document.querySelector("#variation-count").value);
  if (!audio && !lyricsFile && !lyricsText) return showError("Add an MP3, lyrics, or both.");

  setBusy(true);
  clearError();
  try {
    const data = new FormData();
    data.set("collection_id", state.collectionId);
    data.set("lyrics_text", lyricsText);
    data.set("variation_count", String(count));
    data.set("mood_path", "auto");
    data.set("run_async", "true");
    if (audio) data.set("audio", audio);
    if (lyricsFile) data.set("lyrics_file", lyricsFile);
    const generation = await request("/api/generations", { method: "POST", body: data });
    state.generation = generation;
    renderGeneration();
    if (terminalStatuses.has(generation.status)) {
      setBusy(false);
      await refreshHistory();
    } else {
      await poll(generation.id);
    }
  } catch (error) {
    setBusy(false);
    showError(error.message);
  }
}

async function poll(id) {
  const token = ++state.pollToken;
  while (token === state.pollToken) {
    try {
      const generation = await request(`/api/generations/${id}`);
      if (token !== state.pollToken) return;
      state.generation = generation;
      renderGeneration();
      if (terminalStatuses.has(generation.status)) {
        setBusy(false);
        await refreshHistory();
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1500));
    } catch (error) {
      setBusy(false);
      showError(error.message);
      return;
    }
  }
}

async function runPath(path, regenerate = false) {
  if (!state.generation) return;
  setBusy(true);
  clearError();
  const count = Number(document.querySelector("#variation-count").value);
  const action = regenerate ? "regenerate" : "generate";
  try {
    state.generation = await request(`/api/generations/${state.generation.id}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mood_path: path, variation_count: count, run_async: true }),
    });
    renderGeneration();
    await poll(state.generation.id);
  } catch (error) {
    setBusy(false);
    showError(error.message);
  }
}

async function retryFailed() {
  if (!state.generation) return;
  setBusy(true);
  clearError();
  try {
    state.generation = await request(`/api/generations/${state.generation.id}/retry?run_async=true`, { method: "POST" });
    renderGeneration();
    await poll(state.generation.id);
  } catch (error) {
    setBusy(false);
    showError(error.message);
  }
}

async function selectVariation(id) {
  try {
    state.generation = await request(`/api/variations/${id}/select`, { method: "POST" });
    renderGeneration();
    await refreshHistory();
  } catch (error) {
    showError(error.message);
  }
}

async function refreshHistory() {
  const data = await request(`/api/collections/${state.collectionId}/versions`);
  renderHistory(data.versions);
}

function renderGeneration() {
  const generation = state.generation;
  if (!generation) return;
  const latestSet = generation.variation_sets[generation.variation_sets.length - 1];
  resultRoot.innerHTML = "";

  const statusRow = element("div", "status-row");
  statusRow.append(element("strong", "", `Version ${generation.version}`));
  statusRow.append(element("span", `status status-${generation.status}`, generation.status.replaceAll("_", " ")));
  if (generation.cache_hit) statusRow.append(element("span", "cache", "cache hit"));
  resultRoot.append(statusRow);

  if (generation.conflict && generation.status === "needs_mood_choice") {
    const conflict = element("div", "conflict");
    conflict.append(element("h3", "", "Music and lyrics point in different directions"));
    conflict.append(element("p", "", generation.conflict.reason));
    const grid = element("div", "choice-grid");
    grid.append(pathButton("audio", generation.conflict.audio_path));
    grid.append(pathButton("lyrics", generation.conflict.lyrics_path));
    conflict.append(grid);
    resultRoot.append(conflict);
  }

  if (generation.last_error) {
    const error = element("div", "error error-detail");
    error.append(element("strong", "", generation.last_error.code || "Generation error"));
    error.append(element("span", "", generation.last_error.message || "A pipeline step failed."));
    const retry = element("button", "", "Retry failed step");
    retry.disabled = state.busy;
    retry.addEventListener("click", retryFailed);
    error.append(retry);
    resultRoot.append(error);
  }

  if (latestSet) {
    const toolbar = element("div", "set-toolbar");
    const label = element("div");
    label.append(element("small", "", `Variation set ${latestSet.set_number}`));
    label.append(element("strong", "", `${latestSet.mood_path}-driven`));
    toolbar.append(label);
    const actions = element("div", "toolbar-actions");
    if (generation.has_audio && generation.has_lyrics) actions.append(regenerateButton("Fresh blend", "blend"));
    if (generation.has_audio) actions.append(regenerateButton("Fresh audio path", "audio"));
    if (generation.has_lyrics) actions.append(regenerateButton("Fresh lyric path", "lyrics"));
    toolbar.append(actions);
    resultRoot.append(toolbar);

    const covers = element("div", "covers");
    for (const variation of latestSet.variations) {
      const card = element("article", variation.selected ? "cover selected" : "cover");
      const image = document.createElement("img");
      image.src = variation.image_url;
      image.alt = `Album cover variation ${variation.position}`;
      card.append(image);
      const actions = element("div", "cover-actions");
      const select = element("button", "", variation.selected ? "Selected" : "Select");
      select.addEventListener("click", () => selectVariation(variation.id));
      const download = element("a", "", "Download");
      download.href = variation.download_url;
      actions.append(select, download);
      card.append(actions);
      covers.append(card);
    }
    resultRoot.append(covers);
  }
}

function renderHistory(versions) {
  historyRoot.innerHTML = "";
  if (!versions.length) {
    historyRoot.append(element("p", "empty compact", "No historical versions yet."));
    return;
  }
  const list = element("div", "history-list");
  for (const version of versions) {
    const button = element("button");
    button.append(element("span", "", `v${version.version}`));
    const source = version.has_audio && version.has_lyrics ? "Audio + lyrics" : version.has_audio ? "Audio" : "Lyrics";
    button.append(element("strong", "", source));
    button.append(element("small", "", `${version.variation_sets.length} variation set(s)`));
    button.append(element("em", "", version.status.replaceAll("_", " ")));
    button.addEventListener("click", async () => {
      state.pollToken += 1;
      state.generation = await request(`/api/generations/${version.id}`);
      renderGeneration();
    });
    list.append(button);
  }
  historyRoot.append(list);
}

function pathButton(path, content) {
  const button = element("button");
  button.disabled = state.busy;
  button.append(element("strong", "", content.label));
  button.append(element("span", "", content.description));
  button.addEventListener("click", () => runPath(path, false));
  return button;
}

function regenerateButton(label, path) {
  const button = element("button", "", label);
  button.disabled = state.busy;
  button.addEventListener("click", () => runPath(path, true));
  return button;
}

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function setBusy(busy) {
  state.busy = busy;
  submitButton.disabled = busy;
  submitButton.textContent = busy ? "Processing…" : "Analyze and generate";
  renderGeneration();
}

function showError(message) {
  formError.textContent = message;
  formError.classList.remove("hidden");
}

function clearError() {
  formError.textContent = "";
  formError.classList.add("hidden");
}
