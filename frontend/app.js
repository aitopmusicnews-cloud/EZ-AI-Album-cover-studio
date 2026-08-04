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
  const title = document.querySelector("#release-title").value.trim();
  const artist = document.querySelector("#artist-name").value.trim();
  const parentalAdvisory = document.querySelector("#parental-advisory").checked;
  const count = Number(document.querySelector("#variation-count").value);
  if (!audio && !lyricsFile && !lyricsText) return showError("Add an MP3, lyrics, or both.");

  setBusy(true);
  clearError();
  try {
    const data = new FormData();
    data.set("collection_id", state.collectionId);
    data.set("lyrics_text", lyricsText);
    data.set("title", title);
    data.set("artist", artist);
    data.set("parental_advisory", String(parentalAdvisory));
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

async function pollForNewSet(id, previousSetCount) {
  const token = ++state.pollToken;
  let newSetSeen = false;
  while (token === state.pollToken) {
    try {
      const generation = await request(`/api/generations/${id}`);
      if (token !== state.pollToken) return;
      state.generation = generation;
      newSetSeen = newSetSeen || generation.variation_sets.length > previousSetCount;
      renderGeneration();
      if (newSetSeen && terminalStatuses.has(generation.status)) {
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

async function generateBetter() {
  if (!state.generation) return;
  const previousSetCount = state.generation.variation_sets.length;
  const latestSet = state.generation.variation_sets[previousSetCount - 1];
  const moodPath = ["blend", "audio", "lyrics"].includes(latestSet?.mood_path)
    ? latestSet.mood_path
    : "blend";
  const count = Number(document.querySelector("#variation-count").value);

  setBusy(true);
  clearError();
  try {
    state.generation = await request(`/api/generations/${state.generation.id}/improve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mood_path: moodPath, variation_count: count, run_async: true }),
    });
    renderGeneration();
    await pollForNewSet(state.generation.id, previousSetCount);
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

  const releaseMeta = element("div", "release-summary");
  if (generation.title) releaseMeta.append(metaChip("Title", generation.title));
  if (generation.artist) releaseMeta.append(metaChip("Artist", generation.artist));
  if (generation.parental_advisory) releaseMeta.append(metaChip("Label", "Parental Advisory"));
  if (releaseMeta.childElementCount) resultRoot.append(releaseMeta);

  if (generation.analysis) resultRoot.append(renderAnalysis(generation.analysis));

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
    const hasWinner = Boolean(
      latestSet.winner_variation_id ||
      latestSet.variations.some(variation => variation.selection_tier === "winner")
    );
    if (hasWinner && latestSet.critic_status !== "failed") {
      const improve = element("button", "generate-better", "Generate Better");
      improve.disabled = state.busy;
      improve.title = "Create a new set using the AI critic's feedback on the current winner";
      improve.addEventListener("click", generateBetter);
      actions.append(improve);
    }
    if (generation.has_audio && generation.has_lyrics) actions.append(regenerateButton("Fresh blend", "blend"));
    if (generation.has_audio) actions.append(regenerateButton("Fresh audio path", "audio"));
    if (generation.has_lyrics) actions.append(regenerateButton("Fresh lyric path", "lyrics"));
    toolbar.append(actions);
    resultRoot.append(toolbar);

    const covers = element("div", "covers");
    for (const variation of latestSet.variations) {
      const card = element("article", variation.selected ? "cover selected" : "cover");
      const tier = variation.selection_tier || (
        variation.id === latestSet.winner_variation_id
          ? "winner"
          : variation.id === latestSet.runner_up_variation_id
            ? "runner_up"
            : ""
      );
      if (tier === "winner") {
        card.append(element("span", "status status-complete", "AI winner"));
      } else if (tier === "runner_up") {
        card.append(element("span", "status status-partial", "AI runner-up"));
      }
      const image = document.createElement("img");
      image.src = variation.image_url;
      image.alt = `Album cover variation ${variation.position}`;
      card.append(image);

      const positioning = variation.market_positioning;
      if (positioning) {
        const market = element("div", "cover-market");
        market.append(element("strong", "", positioning.lane || "Market position"));
        if (positioning.release_signal) market.append(element("span", "", positioning.release_signal));
        if (positioning.target_audience) market.append(element("small", "", positioning.target_audience));
        card.append(market);
      }

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
    const release = [version.artist, version.title].filter(Boolean).join(" — ");
    button.append(element("strong", "", release || source));
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

function metaChip(label, value) {
  const chip = element("span", "meta-chip");
  chip.append(element("small", "", label));
  chip.append(element("strong", "", value));
  return chip;
}

function renderAnalysis(analysis) {
  const section = element("section", "analysis-card");
  section.append(element("h3", "", "Detected signal"));
  const grid = element("div", "analysis-grid");
  const audio = analysis.audio;
  const lyrics = analysis.lyrics;

  if (audio) {
    grid.append(metric("BPM", formatNumber(audio.tempo_bpm, 1), confidenceText(audio.tempo_confidence)));
    grid.append(metric("Key", `${audio.key || "?"} ${audio.scale || ""}`.trim(), confidenceText(audio.key_confidence)));
    grid.append(metric("Energy", `${Math.round((audio.energy || 0) * 100)}%`, audio.mood?.label || ""));
    grid.append(metric("Loudness", `${formatNumber(audio.loudness_dbfs, 1)} dBFS`, `dynamic range ${formatNumber(audio.dynamic_range_db, 1)} dB`));
    grid.append(metric("Genre / style", audio.inferred_genre || "unknown", confidenceText(audio.genre_confidence)));
    grid.append(metric("Audio mood", audio.mood?.label || "unknown", confidenceText(audio.mood?.confidence)));
  }
  if (lyrics) {
    grid.append(metric("Lyric mood", lyrics.mood?.label || "unknown", confidenceText(lyrics.mood?.confidence)));
    grid.append(metric("Themes", (lyrics.themes || []).slice(0, 3).join(", ") || "none detected", (lyrics.tone || []).slice(0, 3).join(", ")));
    grid.append(metric("Keywords", (lyrics.keywords || []).slice(0, 6).join(", ") || "none detected", ""));
  }
  section.append(grid);
  const note = element("p", "analysis-note", "Audio genre and mood are estimates; BPM, loudness and spectral values are measured. The prompt blends audio and lyrics equally when both are supplied.");
  section.append(note);
  return section;
}

function metric(label, value, detail = "") {
  const card = element("div", "metric");
  card.append(element("small", "", label));
  card.append(element("strong", "", String(value ?? "—")));
  if (detail) card.append(element("span", "", detail));
  return card;
}

function confidenceText(value) {
  if (value === undefined || value === null) return "";
  return `${Math.round(Number(value) * 100)}% confidence`;
}

function formatNumber(value, digits = 1) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "—";
}
