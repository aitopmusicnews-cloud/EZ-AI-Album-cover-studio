(() => {
  const benchmarksByImage = new Map();
  const originalFetch = window.fetch.bind(window);

  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      response.clone().json().then(indexPayload).catch(() => undefined);
    }
    return response;
  };

  function indexPayload(payload) {
    if (!payload || typeof payload !== "object") return;
    if (Array.isArray(payload)) {
      payload.forEach(indexPayload);
      return;
    }
    if (Array.isArray(payload.versions)) payload.versions.forEach(indexGeneration);
    if (Array.isArray(payload.variation_sets)) indexGeneration(payload);
    if (payload.generation) indexGeneration(payload.generation);
    decorateCards();
  }

  function indexGeneration(generation) {
    for (const set of generation?.variation_sets || []) {
      for (const variation of set.variations || []) {
        const benchmark = variation.commercial_benchmark
          || variation.market_positioning?.commercial_benchmark;
        if (benchmark && variation.image_url) {
          benchmarksByImage.set(normalizePath(variation.image_url), benchmark);
        }
      }
    }
  }

  function normalizePath(url) {
    try {
      return new URL(url, window.location.origin).pathname;
    } catch {
      return String(url || "");
    }
  }

  function decorateCards() {
    for (const card of document.querySelectorAll(".cover")) {
      if (card.querySelector(".commercial-benchmark")) continue;
      const image = card.querySelector("img");
      const benchmark = image ? benchmarksByImage.get(normalizePath(image.src)) : null;
      if (!benchmark) continue;

      const panel = document.createElement("section");
      panel.className = "commercial-benchmark";

      const heading = document.createElement("div");
      heading.className = "commercial-benchmark-heading";

      const grade = document.createElement("strong");
      grade.className = "commercial-grade";
      grade.textContent = benchmark.grade || "—";

      const summary = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = `${formatScore(benchmark.score)} / 100`;
      const readiness = document.createElement("span");
      readiness.textContent = benchmark.release_readiness || "benchmark pending";
      summary.append(title, readiness);
      heading.append(grade, summary);
      panel.append(heading);

      const track = document.createElement("div");
      track.className = "commercial-score-track";
      const fill = document.createElement("span");
      fill.style.width = `${clampScore(benchmark.score)}%`;
      track.append(fill);
      panel.append(track);

      const band = document.createElement("small");
      band.textContent = benchmark.percentile_band || benchmark.rubric || "Internal release benchmark";
      panel.append(band);

      if (Array.isArray(benchmark.improvement_gaps) && benchmark.improvement_gaps.length) {
        const gap = document.createElement("p");
        gap.textContent = benchmark.improvement_gaps[0];
        panel.append(gap);
      } else if (benchmark.next_action) {
        const action = document.createElement("p");
        action.textContent = benchmark.next_action;
        panel.append(action);
      }

      const actions = card.querySelector(".cover-actions");
      card.insertBefore(panel, actions || null);
    }
  }

  function formatScore(value) {
    const score = Number(value);
    return Number.isFinite(score) ? score.toFixed(1) : "—";
  }

  function clampScore(value) {
    const score = Number(value);
    return Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
  }

  new MutationObserver(decorateCards).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  window.addEventListener("load", decorateCards);
})();
