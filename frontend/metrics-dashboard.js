(() => {
  const root = document.querySelector("#metrics-dashboard");
  let refreshInFlight = false;

  function node(tag, className = "", text = "") {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== "") item.textContent = String(text);
    return item;
  }

  function collectionId() {
    const existing = localStorage.getItem("album-cover-collection");
    if (existing) return existing;
    const created = crypto.randomUUID().replaceAll("-", "");
    localStorage.setItem("album-cover-collection", created);
    return created;
  }

  function formatScore(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(1) : "—";
  }

  function formatPercent(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(1)}%` : "0.0%";
  }

  function labelPlatform(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, letter => letter.toUpperCase());
  }

  function summaryCard(label, value, detail = "") {
    const card = node("article", "dashboard-summary-card");
    card.append(node("small", "", label));
    card.append(node("strong", "", value));
    if (detail) card.append(node("span", "", detail));
    return card;
  }

  function operationalMetric(label, value) {
    const item = node("div", "dashboard-operational-item");
    item.append(node("span", "", label));
    item.append(node("strong", "", value));
    return item;
  }

  function renderPlatforms(container, platforms) {
    const entries = Object.entries(platforms || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
    if (!entries.length) {
      container.append(node("p", "dashboard-empty", "Platform scores appear after the cover critic finishes."));
      return;
    }

    for (const [platform, rawScore] of entries) {
      const score = Math.max(0, Math.min(100, Number(rawScore) || 0));
      const row = node("div", "dashboard-bar-row");
      const header = node("div", "dashboard-bar-label");
      header.append(node("span", "", labelPlatform(platform)));
      header.append(node("strong", "", score.toFixed(1)));
      const track = node("div", "dashboard-bar-track");
      const fill = node("span", "dashboard-bar-fill");
      fill.style.width = `${score}%`;
      track.append(fill);
      row.append(header, track);
      container.append(row);
    }
  }

  function renderTrend(container, trend) {
    const points = (trend || []).filter(point => point.winner_score != null || point.average_score != null);
    if (!points.length) {
      container.append(node("p", "dashboard-empty", "Quality trends appear after scored variation sets are completed."));
      return;
    }

    for (const point of points) {
      const score = Number(point.winner_score ?? point.average_score ?? 0);
      const row = node("div", "dashboard-trend-row");
      row.append(node("span", "dashboard-trend-label", `v${point.version} · set ${point.set_number}`));
      const track = node("div", "dashboard-trend-track");
      const fill = node("span", "dashboard-trend-fill");
      fill.style.width = `${Math.max(0, Math.min(100, score))}%`;
      track.append(fill);
      row.append(track, node("strong", "dashboard-trend-score", score.toFixed(1)));
      container.append(row);
    }
  }

  window.renderMetricsDashboard = function renderMetricsDashboard(metrics) {
    if (!root) return;
    root.innerHTML = "";

    const summary = node("div", "dashboard-summary-grid");
    summary.append(
      summaryCard("Covers generated", metrics.covers_generated || 0, `${metrics.scored_covers || 0} scored`),
      summaryCard("Average cover score", formatScore(metrics.average_cover_score), `Best ${formatScore(metrics.best_cover_score)}`),
      summaryCard("Successful versions", formatPercent(metrics.success_rate), `${metrics.successful_versions || 0} of ${metrics.versions || 0}`),
      summaryCard("Release-ready covers", metrics.release_ready_covers || 0, "Commercial ≥80 · cover ≥75"),
    );
    root.append(summary);

    const body = node("div", "dashboard-body-grid");

    const operations = node("section", "dashboard-block");
    operations.append(node("h3", "", "Pipeline health"));
    const operationalGrid = node("div", "dashboard-operational-grid");
    operationalGrid.append(
      operationalMetric("Input versions", metrics.versions || 0),
      operationalMetric("Variation sets", metrics.variation_sets || 0),
      operationalMetric("Critic complete", formatPercent(metrics.critic_completion_rate)),
      operationalMetric("Avg thumbnail", formatScore(metrics.average_thumbnail_score)),
      operationalMetric("Avg commercial", formatScore(metrics.average_commercial_score)),
      operationalMetric("Selected covers", metrics.selected_covers || 0),
      operationalMetric("Retries", metrics.retries || 0),
      operationalMetric("Failed steps", metrics.failed_steps || 0),
    );
    operations.append(operationalGrid);

    const platforms = node("section", "dashboard-block");
    platforms.append(node("h3", "", "Platform averages"));
    const platformList = node("div", "dashboard-bars");
    renderPlatforms(platformList, metrics.platform_averages);
    platforms.append(platformList);

    const trend = node("section", "dashboard-block dashboard-trend-block");
    trend.append(node("h3", "", "Recent quality trend"));
    const trendList = node("div", "dashboard-trend-list");
    renderTrend(trendList, metrics.quality_trend);
    trend.append(trendList);

    body.append(operations, platforms, trend);
    root.append(body);
  };

  window.refreshMetricsDashboard = async function refreshMetricsDashboard() {
    if (!root || refreshInFlight || document.hidden) return;
    refreshInFlight = true;
    try {
      const response = await fetch(`/api/collections/${collectionId()}/metrics`);
      if (!response.ok) return;
      window.renderMetricsDashboard(await response.json());
    } catch (_error) {
      // The main generation UI remains usable if metrics are temporarily unavailable.
    } finally {
      refreshInFlight = false;
    }
  };

  window.refreshMetricsDashboard();
  window.setInterval(window.refreshMetricsDashboard, 5000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) window.refreshMetricsDashboard();
  });
})();
