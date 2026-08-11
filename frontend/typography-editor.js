const FONT_OPTIONS = [
  "Allura", "Armadillo", "Baksoap", "Butflow", "Chainsaw Carnage",
  "Chopin Script", "Contour Generator", "Corleone", "Corleone Due",
  "Dystopian Canticle", "Ferro Rosso", "Heart Breaking Bad", "Homoarakhn",
  "If", "League Gothic", "League Gothic Condensed", "Libre Baskerville",
  "Magnolia Script", "Marlboro", "Miltown", "Montserrat", "Pixemon",
  "Poppins", "Punk Kid", "Ranch Mails", "The Battle Continuez",
  "The Rave Is In Your Pants", "Underground", "Bold Doodle", "Great Vibes",
  "Jo Wrote a Lovesong", "Lora", "Chunk Five", "Chunk Five Print",
  "Lexographer", "CMU Serif", "CMU Sans", "CMU Typewriter",
  "League Gothic Italic", "League Gothic Condensed Italic",
  "Libre Baskerville Bold", "Libre Baskerville Italic",
  "Montserrat Regular", "Montserrat Black", "Montserrat Italic",
  "Poppins Regular", "Poppins Black", "Poppins Italic",
  "Lora Bold", "Lora Italic", "Lora Bold Italic", "CMU Serif Bold", "CMU Sans Bold",
];

let editor;

export function openTypographyEditor(options) {
  if (!editor) editor = createEditor();
  editor.open(options);
}

function createEditor() {
  const modal = document.createElement("div");
  modal.className = "type-editor-modal hidden";
  modal.innerHTML = `
    <section class="type-editor-shell" role="dialog" aria-modal="true" aria-label="Typography editor">
      <div class="type-editor-head"><h2>Editable typography studio</h2><button type="button" data-action="close">Close</button></div>
      <div class="type-editor-grid">
        <div class="type-canvas-wrap"><canvas width="1000" height="1000"></canvas></div>
        <aside class="type-controls">
          <p class="type-help">Click a text layer, then drag it anywhere on the cover. Every setting remains editable until you export.</p>
          <div class="type-layer-list"></div>
          <div class="type-layer-actions">
            <button type="button" data-action="add">Add text</button>
            <button type="button" data-action="front">Bring forward</button>
            <button type="button" data-action="back">Send backward</button>
            <button type="button" data-action="delete">Delete</button>
          </div>
          <label>Text<textarea data-field="text" rows="3" maxlength="200"></textarea></label>
          <label>Font <span data-font-count></span>
            <div class="font-picker">
              <button type="button" class="font-picker-toggle" data-action="font-picker"><span data-font-current></span><span>⌄</span></button>
              <div class="font-picker-menu hidden">
                <input type="search" data-font-search placeholder="Search fonts…" autocomplete="off">
                <div class="font-preview-list" data-font-options></div>
              </div>
            </div>
          </label>
          <div class="type-control-grid">
            <label>Size <span data-value="size"></span><input data-field="size" type="range" min="16" max="240" step="1"></label>
            <label>Rotation <span data-value="rotation"></span><input data-field="rotation" type="range" min="-180" max="180" step="1"></label>
            <label>Letter spacing <span data-value="spacing"></span><input data-field="spacing" type="range" min="-5" max="40" step="1"></label>
            <label>Opacity <span data-value="opacity"></span><input data-field="opacity" type="range" min="10" max="100" step="1"></label>
            <label>Text color<input data-field="color" type="color"></label>
            <label>Outline color<input data-field="strokeColor" type="color"></label>
            <label>Outline <span data-value="strokeWidth"></span><input data-field="strokeWidth" type="range" min="0" max="18" step="1"></label>
            <label>Alignment<select data-field="align"><option value="left">Left</option><option value="center">Center</option><option value="right">Right</option></select></label>
          </div>
          <div class="type-checks">
            <label class="checkbox-row"><input data-field="shadow" type="checkbox"><span>Shadow</span></label>
            <label class="checkbox-row"><input data-field="uppercase" type="checkbox"><span>ALL CAPS</span></label>
          </div>
        </aside>
      </div>
      <div class="type-editor-actions">
        <button type="button" data-action="reset">Reset design</button>
        <button type="button" data-action="save">Save edits</button>
        <button type="button" class="primary" data-action="download">Export 3000×3000 PNG</button>
      </div>
    </section>`;
  document.body.append(modal);

  const canvas = modal.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  renderFontOptions(modal, FONT_OPTIONS);

  const api = {
    modal, canvas, ctx, background: null, variationId: "", releaseTitle: "", selected: 0,
    defaults: [], layers: [], drag: null,
    async open({ variationId, imageUrl, title, artist }) {
      this.variationId = variationId;
      this.releaseTitle = title || "Album Cover";
      this.defaults = defaultLayers(title, artist);
      this.layers = loadLayers(variationId) || structuredClone(this.defaults);
      this.selected = 0;
      this.background = await loadImage(imageUrl);
      modal.classList.remove("hidden");
      document.body.classList.add("type-editor-open");
      resetFontSearch(modal);
      syncControls(this);
      await document.fonts.ready;
      draw(this);
    },
    close() {
      modal.classList.add("hidden");
      document.body.classList.remove("type-editor-open");
    },
  };

  modal.addEventListener("click", event => {
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (!action) return;
    if (action === "close") api.close();
    if (action === "font-picker") {
      modal.querySelector(".font-picker-menu").classList.toggle("hidden");
      if (!modal.querySelector(".font-picker-menu").classList.contains("hidden")) {
        modal.querySelector("[data-font-search]").focus();
      }
    }
    if (action === "add") {
      api.layers.push(makeLayer("Custom text", "Poppins", 64, 500, 500));
      api.selected = api.layers.length - 1;
      syncControls(api); draw(api);
    }
    if (action === "delete" && api.layers.length > 1) {
      api.layers.splice(api.selected, 1); api.selected = Math.max(0, api.selected - 1);
      syncControls(api); draw(api);
    }
    if (action === "front" && api.selected < api.layers.length - 1) {
      [api.layers[api.selected], api.layers[api.selected + 1]] = [api.layers[api.selected + 1], api.layers[api.selected]];
      api.selected += 1; syncControls(api); draw(api);
    }
    if (action === "back" && api.selected > 0) {
      [api.layers[api.selected], api.layers[api.selected - 1]] = [api.layers[api.selected - 1], api.layers[api.selected]];
      api.selected -= 1; syncControls(api); draw(api);
    }
    if (action === "reset") {
      api.layers = structuredClone(api.defaults); api.selected = 0;
      syncControls(api); draw(api);
    }
    if (action === "save") {
      localStorage.setItem(storageKey(api.variationId), JSON.stringify(api.layers));
      event.target.textContent = "Saved";
      setTimeout(() => { event.target.textContent = "Save edits"; }, 1200);
    }
    if (action === "download") exportPng(api);
  });

  modal.addEventListener("input", event => {
    const field = event.target.dataset.field;
    if (!field || !api.layers[api.selected]) return;
    const layer = api.layers[api.selected];
    layer[field] = event.target.type === "checkbox" ? event.target.checked
      : event.target.type === "range" ? Number(event.target.value) : event.target.value;
    updateValueLabels(modal, layer);
    document.fonts.load(`${layer.size}px "${layer.font}"`).then(() => draw(api));
  });

  modal.querySelector(".type-layer-list").addEventListener("click", event => {
    const index = Number(event.target.closest("button")?.dataset.index);
    if (!Number.isInteger(index)) return;
    api.selected = index; syncControls(api); draw(api);
  });

  modal.querySelector("[data-font-options]").addEventListener("click", event => {
    const button = event.target.closest("[data-font-family]");
    if (!button) return;
    const layer = api.layers[api.selected];
    layer.font = button.dataset.fontFamily;
    modal.querySelector(".font-picker-menu").classList.add("hidden");
    syncControls(api);
    document.fonts.load(`${layer.size}px "${layer.font}"`).then(() => draw(api));
  });

  modal.querySelector("[data-font-search]").addEventListener("input", event => {
    const query = event.target.value.trim().toLowerCase();
    for (const option of modal.querySelectorAll("[data-font-family]")) {
      option.hidden = Boolean(query) && !option.dataset.fontFamily.toLowerCase().includes(query);
    }
  });

  canvas.addEventListener("pointerdown", event => {
    const point = canvasPoint(canvas, event);
    const hit = findLayer(api, point.x, point.y);
    if (hit < 0) return;
    api.selected = hit;
    const layer = api.layers[hit];
    api.drag = { dx: point.x - layer.x, dy: point.y - layer.y };
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add("dragging");
    syncControls(api); draw(api);
  });
  canvas.addEventListener("pointermove", event => {
    if (!api.drag) return;
    const point = canvasPoint(canvas, event);
    const layer = api.layers[api.selected];
    layer.x = clamp(point.x - api.drag.dx, 0, 1000);
    layer.y = clamp(point.y - api.drag.dy, 0, 1000);
    draw(api);
  });
  const endDrag = () => { api.drag = null; canvas.classList.remove("dragging"); };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  return api;
}

function defaultLayers(title, artist) {
  return [
    { ...makeLayer(title, "Magnolia Script", 112, 500, 175), name: "Title", strokeWidth: 3, shadow: true },
    { ...makeLayer(artist, "League Gothic", 46, 500, 870), name: "Artist", spacing: 5, uppercase: true },
    { ...makeLayer("Text 3", "Bold Doodle", 58, 250, 700), name: "Text 3" },
    { ...makeLayer("Text 4", "Great Vibes", 64, 750, 700), name: "Text 4" },
  ];
}

function makeLayer(text, font, size, x, y) {
  return { name: "Text", text, font, size, x, y, color: "#fff4df", strokeColor: "#111111", strokeWidth: 2, rotation: 0, spacing: 0, opacity: 100, align: "center", shadow: false, uppercase: false };
}

function syncControls(api) {
  const layer = api.layers[api.selected];
  const list = api.modal.querySelector(".type-layer-list");
  list.innerHTML = "";
  api.layers.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button"; button.dataset.index = index;
    button.className = index === api.selected ? "active" : "";
    button.textContent = item.name || `Text ${index + 1}`;
    list.append(button);
  });
  for (const input of api.modal.querySelectorAll("[data-field]")) {
    const value = layer[input.dataset.field];
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = value;
  }
  api.modal.querySelector("[data-font-current]").textContent = layer.font;
  api.modal.querySelector(".font-picker-toggle").style.fontFamily = `"${layer.font}"`;
  for (const option of api.modal.querySelectorAll("[data-font-family]")) {
    option.classList.toggle("active", option.dataset.fontFamily === layer.font);
  }
  updateValueLabels(api.modal, layer);
  api.modal.querySelector('[data-action="delete"]').disabled = api.layers.length <= 1;
}

function updateValueLabels(modal, layer) {
  const values = { size: `${layer.size}px`, rotation: `${layer.rotation}°`, spacing: `${layer.spacing}px`, opacity: `${layer.opacity}%`, strokeWidth: `${layer.strokeWidth}px` };
  for (const [field, value] of Object.entries(values)) modal.querySelector(`[data-value="${field}"]`).textContent = value;
}

function renderFontOptions(modal, families) {
  const root = modal.querySelector("[data-font-options]");
  for (const family of families) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "font-preview-option";
    button.dataset.fontFamily = family;
    button.style.setProperty("--preview-font", `"${family}"`);
    const name = document.createElement("small");
    name.textContent = family;
    const preview = document.createElement("strong");
    preview.textContent = "Album Title";
    button.append(name, preview);
    root.append(button);
  }
}

function draw(api, target = api.ctx, scale = 1, showSelection = true) {
  const width = 1000 * scale;
  target.clearRect(0, 0, width, width);
  target.drawImage(api.background, 0, 0, width, width);
  api.layers.forEach((layer, index) => drawLayer(target, layer, scale, showSelection && index === api.selected));
}

function drawLayer(ctx, layer, scale, selected) {
  const text = layer.uppercase ? layer.text.toUpperCase() : layer.text;
  const lines = text.split("\n");
  ctx.save();
  ctx.translate(layer.x * scale, layer.y * scale);
  ctx.rotate(layer.rotation * Math.PI / 180);
  ctx.globalAlpha = layer.opacity / 100;
  ctx.font = `${layer.size * scale}px "${layer.font}"`;
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  if (layer.shadow) {
    ctx.shadowColor = "rgba(0,0,0,.75)";
    ctx.shadowBlur = 10 * scale;
    ctx.shadowOffsetX = 6 * scale;
    ctx.shadowOffsetY = 7 * scale;
  }
  const lineHeight = layer.size * 1.12 * scale;
  const totalHeight = lineHeight * lines.length;
  let widest = 0;
  lines.forEach((line, index) => {
    const width = trackedWidth(ctx, line, layer.spacing * scale);
    widest = Math.max(widest, width);
    const start = layer.align === "left" ? 0 : layer.align === "right" ? -width : -width / 2;
    const y = index * lineHeight - totalHeight / 2 + lineHeight / 2;
    drawTracked(ctx, line, start, y, layer.spacing * scale, layer);
  });
  ctx.shadowColor = "transparent";
  if (selected) {
    ctx.globalAlpha = 1;
    ctx.strokeStyle = "#ff9d45";
    ctx.lineWidth = 2 * scale;
    const left = layer.align === "left" ? 0 : layer.align === "right" ? -widest : -widest / 2;
    ctx.setLineDash([8 * scale, 5 * scale]);
    ctx.strokeRect(left - 12 * scale, -totalHeight / 2 - 8 * scale, widest + 24 * scale, totalHeight + 16 * scale);
  }
  ctx.restore();
}

function drawTracked(ctx, text, x, y, spacing, layer) {
  let cursor = x;
  for (const character of text) {
    if (layer.strokeWidth > 0) {
      ctx.strokeStyle = layer.strokeColor;
      ctx.lineWidth = layer.strokeWidth * 2;
      ctx.strokeText(character, cursor, y);
    }
    ctx.fillStyle = layer.color;
    ctx.fillText(character, cursor, y);
    cursor += ctx.measureText(character).width + spacing;
  }
}

function trackedWidth(ctx, text, spacing) {
  return [...text].reduce((sum, character, index) => sum + ctx.measureText(character).width + (index ? spacing : 0), 0);
}

function findLayer(api, x, y) {
  for (let index = api.layers.length - 1; index >= 0; index -= 1) {
    const layer = api.layers[index];
    api.ctx.font = `${layer.size}px "${layer.font}"`;
    const width = Math.max(...layer.text.split("\n").map(line => trackedWidth(api.ctx, line, layer.spacing)), 80);
    const height = Math.max(layer.size * 1.2 * layer.text.split("\n").length, 50);
    if (Math.abs(x - layer.x) <= width / 2 + 30 && Math.abs(y - layer.y) <= height / 2 + 30) return index;
  }
  return -1;
}

async function exportPng(api) {
  await Promise.all(api.layers.map(layer => document.fonts.load(`${layer.size}px "${layer.font}"`)));
  const output = document.createElement("canvas");
  output.width = 3000; output.height = 3000;
  draw(api, output.getContext("2d"), 3, false);
  output.toBlob(blob => {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${downloadFilename(api.releaseTitle)}.png`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }, "image/png");
}

function downloadFilename(title) {
  const clean = String(title || "Album Cover")
    .replace(/[\\/:*?"<>|]+/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\.+$/g, "")
    .slice(0, 120);
  return clean || "Album Cover";
}

function resetFontSearch(modal) {
  modal.querySelector("[data-font-search]").value = "";
  for (const option of modal.querySelectorAll("[data-font-family]")) option.hidden = false;
  modal.querySelector("[data-font-count]").textContent = `(${FONT_OPTIONS.length} available)`;
}

function loadLayers(id) {
  try { return JSON.parse(localStorage.getItem(storageKey(id))); } catch { return null; }
}
function storageKey(id) { return `ez-typography-editor-v1:${id}`; }
function loadImage(source) { return new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error("Cover image could not be loaded.")); image.src = source; }); }
function canvasPoint(canvas, event) { const box = canvas.getBoundingClientRect(); return { x: (event.clientX - box.left) * 1000 / box.width, y: (event.clientY - box.top) * 1000 / box.height }; }
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
