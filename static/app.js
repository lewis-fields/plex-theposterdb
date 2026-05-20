const state = {
  libraries: [],
  items: [],
  seasonsByShow: {},
  loadingSeasons: new Set(),
  posters: [],
  selectedItem: null,
  selectedTargetUrl: "",
  busy: false,
};

const elements = {
  configForm: document.querySelector("#configForm"),
  plexUrl: document.querySelector("#plexUrl"),
  plexToken: document.querySelector("#plexToken"),
  pathMappings: document.querySelector("#pathMappings"),
  connectionState: document.querySelector("#connectionState"),
  loadLibraries: document.querySelector("#loadLibraries"),
  librarySelect: document.querySelector("#librarySelect"),
  libraryCount: document.querySelector("#libraryCount"),
  refreshItems: document.querySelector("#refreshItems"),
  itemFilter: document.querySelector("#itemFilter"),
  itemCount: document.querySelector("#itemCount"),
  status: document.querySelector("#status"),
  itemsList: document.querySelector("#itemsList"),
  selectedTitle: document.querySelector("#selectedTitle"),
  selectedMeta: document.querySelector("#selectedMeta"),
  searchTpdb: document.querySelector("#searchTpdb"),
  tpdbSearchTerm: document.querySelector("#tpdbSearchTerm"),
  creatorFilter: document.querySelector("#creatorFilter"),
  targetList: document.querySelector("#targetList"),
  posterGrid: document.querySelector("#posterGrid"),
};

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("error", isError);
  elements.status.classList.toggle("success", Boolean(message) && !isError);
}

function setBusy(isBusy) {
  state.busy = isBusy;
  document.body.classList.toggle("busy", isBusy);
  for (const button of document.querySelectorAll("button")) {
    button.disabled = isBusy || button.dataset.locked === "true";
  }
  elements.searchTpdb.disabled = isBusy || !state.selectedItem;
  elements.tpdbSearchTerm.disabled = !state.selectedItem;
  elements.creatorFilter.disabled = state.posters.length === 0;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function parseMappings(value) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [plex, local] = line.split("=>").map((part) => part.trim());
      return { plex, local };
    })
    .filter((mapping) => mapping.plex && mapping.local);
}

function formatMappings(mappings) {
  return (mappings || []).map((mapping) => `${mapping.plex} => ${mapping.local}`).join("\n");
}

async function loadConfig() {
  const config = await api("/api/config");
  elements.plexUrl.value = config.plex_url || "";
  elements.plexToken.value = config.plex_token || "";
  elements.pathMappings.value = formatMappings(config.path_mappings || []);
  elements.connectionState.textContent = config.plex_url && config.plex_token ? "Configured" : "Not configured";
  elements.connectionState.classList.toggle("ok", Boolean(config.plex_url && config.plex_token));
}

async function saveConfig(event) {
  event.preventDefault();
  await api("/api/config", {
    method: "POST",
    body: JSON.stringify({
      plex_url: elements.plexUrl.value.trim(),
      plex_token: elements.plexToken.value.trim(),
      path_mappings: parseMappings(elements.pathMappings.value),
    }),
  });
  elements.connectionState.textContent = "Configured";
  elements.connectionState.classList.add("ok");
  setStatus("Connection saved.");
}

async function loadLibraries() {
  setStatus("Loading Plex libraries...");
  const payload = await api("/api/libraries");
  state.libraries = payload.libraries;
  elements.librarySelect.innerHTML = "";
  for (const library of state.libraries) {
    const option = document.createElement("option");
    option.value = library.key;
    option.textContent = `${library.title} (${library.type})`;
    elements.librarySelect.append(option);
  }
  elements.libraryCount.textContent = `${state.libraries.length} loaded`;
  setStatus(state.libraries.length ? "Libraries loaded." : "No movie or show libraries found.");
  if (state.libraries.length) {
    await loadItems();
  }
}

async function loadItems() {
  const section = elements.librarySelect.value;
  if (!section) return;
  setStatus("Loading Plex items...");
  const payload = await api(`/api/items?section=${encodeURIComponent(section)}`);
  state.items = payload.items;
  state.seasonsByShow = {};
  state.loadingSeasons = new Set();
  renderItems();
  clearPosterPane();
  setStatus(`${state.items.length} items loaded.`);
}

async function loadSeasons(show) {
  if (state.seasonsByShow[show.ratingKey] || state.loadingSeasons.has(show.ratingKey)) return;
  state.loadingSeasons.add(show.ratingKey);
  renderItems();
  try {
    const payload = await api(`/api/seasons?show=${encodeURIComponent(show.ratingKey)}`);
    state.seasonsByShow[show.ratingKey] = payload.seasons;
  } finally {
    state.loadingSeasons.delete(show.ratingKey);
    renderItems();
  }
}

function renderItems() {
  const filter = elements.itemFilter.value.trim().toLowerCase();
  const items = state.items.filter((item) => {
    return !filter || `${item.title} ${item.year}`.toLowerCase().includes(filter);
  });

  elements.itemsList.innerHTML = "";
  elements.itemsList.classList.toggle("empty", items.length === 0);
  elements.itemCount.textContent = state.items.length
    ? `${items.length} shown from ${state.items.length}`
    : "No items loaded";
  if (!items.length) {
    elements.itemsList.innerHTML = `<div class="emptyState">${state.items.length ? "No items match the current filter." : "No items loaded."}</div>`;
    return;
  }

  for (const item of items) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "itemRow";
    row.classList.toggle("active", state.selectedItem?.ratingKey === item.ratingKey);
    row.innerHTML = `
      <span class="itemText">
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(item.file || "No media path exposed")}</span>
      </span>
      <span class="itemMeta">${escapeHtml(item.year || item.type)}</span>
    `;
    row.addEventListener("click", () => selectItem(item));
    elements.itemsList.append(row);
    if (item.type === "show") {
      renderSeasonRows(item);
    }
  }
}

function renderSeasonRows(show) {
  const seasons = state.seasonsByShow[show.ratingKey];
  if (state.loadingSeasons.has(show.ratingKey)) {
    const loading = document.createElement("div");
    loading.className = "seasonHint";
    loading.textContent = "Loading seasons...";
    elements.itemsList.append(loading);
    return;
  }
  if (!seasons) return;
  for (const season of seasons) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "itemRow seasonRow";
    row.classList.toggle("active", state.selectedItem?.ratingKey === season.ratingKey);
    row.innerHTML = `
      <span class="itemText">
        <strong>${escapeHtml(season.title)}</strong>
        <span>${escapeHtml(season.folder || season.file || "No season folder exposed")}</span>
      </span>
      <span class="itemMeta">${season.index === "0" ? "Specials" : `S${String(season.index || "").padStart(2, "0")}`}</span>
    `;
    row.addEventListener("click", () => selectItem(season));
    elements.itemsList.append(row);
  }
}

function selectItem(item) {
  state.selectedItem = item;
  state.selectedTargetUrl = "";
  state.posters = [];
  const displayTitle = item.type === "season" ? `${item.parentTitle} · ${item.title}` : `${item.title}${item.year ? ` (${item.year})` : ""}`;
  elements.selectedTitle.textContent = displayTitle;
  elements.selectedMeta.textContent = selectedItemMeta(item);
  elements.tpdbSearchTerm.value = item.searchTitle || item.parentTitle || item.title;
  elements.creatorFilter.value = "";
  elements.searchTpdb.disabled = false;
  elements.tpdbSearchTerm.disabled = false;
  elements.creatorFilter.disabled = true;
  elements.targetList.innerHTML = "";
  elements.posterGrid.innerHTML = '<div class="emptyState">Search TPDb to load poster choices.</div>';
  elements.posterGrid.classList.add("empty");
  if (item.type === "show") {
    run(() => loadSeasons(item));
  }
  renderItems();
}

async function searchTpdb() {
  if (!state.selectedItem) return;
  setStatus("Searching TPDb...");
  elements.targetList.innerHTML = "";
  elements.posterGrid.innerHTML = loadingMarkup("Searching TPDb");
  elements.posterGrid.classList.add("empty");
  const term = elements.tpdbSearchTerm.value.trim() || state.selectedItem.title;
  const payload = await api(
    `/api/tpdb/search?term=${encodeURIComponent(term)}&type=${encodeURIComponent(state.selectedItem.type)}`,
  );
  renderTargets(payload.targets);
  setStatus(payload.targets.length ? "Choose a TPDb result." : "No TPDb search results found.");
}

function renderTargets(targets) {
  elements.targetList.innerHTML = "";
  if (!targets.length) {
    elements.posterGrid.innerHTML = '<div class="emptyState">No TPDb result matched this title.</div>';
    return;
  }
  for (const target of targets) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "target";
    button.textContent = target.title;
    button.title = target.title;
    button.addEventListener("click", () => loadPosters(target.url, button));
    elements.targetList.append(button);
  }
  elements.targetList.querySelector(".target")?.click();
}

async function loadPosters(url, activeButton) {
  const posterUrl = posterUrlForSelection(url);
  state.selectedTargetUrl = posterUrl;
  for (const button of elements.targetList.querySelectorAll(".target")) {
    button.classList.toggle("active", button === activeButton);
  }
  const loadingLabel = state.selectedItem?.type === "season" ? "Loading season poster pages" : "Loading poster pages";
  setStatus(loadingLabel + "...");
  elements.posterGrid.innerHTML = loadingMarkup(loadingLabel);
  const payload = await api(`/api/tpdb/posters?url=${encodeURIComponent(posterUrl)}`);
  state.posters = payload.posters;
  elements.creatorFilter.disabled = state.posters.length === 0;
  renderPosters(payload.posters);
  if (!payload.posters.length) {
    setStatus("No posters found on that TPDb page.");
    return;
  }
  const pageText = `${payload.pagesFetched || 1} TPDb page${payload.pagesFetched === 1 ? "" : "s"}`;
  const moreText = payload.hasMore ? ` Max page limit reached at ${payload.maxPages}.` : "";
  const scopeText = state.selectedItem?.type === "season" ? "season posters" : "posters";
  setStatus(`${payload.posters.length} ${scopeText} found across ${pageText}.${moreText}`);
}

function posterUrlForSelection(url) {
  if (state.selectedItem?.type !== "season") {
    return url;
  }
  const posterUrl = new URL(url);
  posterUrl.searchParams.set("season", state.selectedItem.index || "0");
  return posterUrl.toString();
}

function renderPosters(posters) {
  const creatorFilter = elements.creatorFilter.value.trim().toLowerCase();
  const visiblePosters = posters.filter((poster) => {
    if (!creatorFilter) return true;
    return `${poster.creator || ""} ${poster.title || ""}`.toLowerCase().includes(creatorFilter);
  });

  elements.posterGrid.innerHTML = "";
  elements.posterGrid.classList.toggle("empty", visiblePosters.length === 0);
  if (!visiblePosters.length) {
    elements.posterGrid.innerHTML = `<div class="emptyState">${posters.length ? "No posters match that creator." : "No poster assets were visible on this page."}</div>`;
    return;
  }
  for (const poster of visiblePosters) {
    const card = document.createElement("article");
    card.className = "posterCard";
    const proxiedImage = `/api/proxy-image?url=${encodeURIComponent(poster.imageUrl)}`;
    card.innerHTML = `
      <img src="${proxiedImage}" alt="${escapeHtml(poster.title)}" loading="lazy" />
      <div class="posterInfo">
        <strong title="${escapeHtml(poster.creator || poster.title)}">${escapeHtml(poster.creator || "Unknown creator")}</strong>
        <span title="${escapeHtml(poster.title)}">${escapeHtml(poster.title)}</span>
        <button class="apply" type="button">Apply poster</button>
      </div>
    `;
    card.querySelector(".apply").addEventListener("click", () => applyPoster(poster.imageUrl));
    elements.posterGrid.append(card);
  }
}

async function applyPoster(imageUrl) {
  if (!state.selectedItem) return;
  setStatus("Downloading poster and refreshing Plex...");
  const payload = await api("/api/apply", {
    method: "POST",
    body: JSON.stringify({ item: state.selectedItem, imageUrl }),
  });
  setStatus(`Poster saved: ${payload.path}`);
}

function selectedItemMeta(item) {
  if (item.type === "season") {
    return `TV season · ${item.folder || item.file || "No season folder exposed"}`;
  }
  if (item.type === "show") {
    return `TV show · ${item.file || "No show folder exposed"}`;
  }
  return `Movie · ${item.file || "No media path exposed"}`;
}

function clearPosterPane() {
  state.selectedItem = null;
  state.selectedTargetUrl = "";
  state.posters = [];
  elements.selectedTitle.textContent = "Select an item";
  elements.selectedMeta.textContent = "Choose a movie or show to begin.";
  elements.searchTpdb.disabled = true;
  elements.tpdbSearchTerm.value = "";
  elements.tpdbSearchTerm.disabled = true;
  elements.creatorFilter.value = "";
  elements.creatorFilter.disabled = true;
  elements.targetList.innerHTML = "";
  elements.posterGrid.innerHTML = '<div class="emptyState">Poster choices will appear here.</div>';
  elements.posterGrid.classList.add("empty");
}

function loadingMarkup(label) {
  return `
    <div class="loadingState">
      <span></span>
      <strong>${escapeHtml(label)}</strong>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function run(task) {
  try {
    setBusy(true);
    await task();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
  }
}

elements.configForm.addEventListener("submit", (event) => run(() => saveConfig(event)));
elements.loadLibraries.addEventListener("click", () => run(loadLibraries));
elements.librarySelect.addEventListener("change", () => run(loadItems));
elements.refreshItems.addEventListener("click", () => run(loadItems));
elements.itemFilter.addEventListener("input", renderItems);
elements.tpdbSearchTerm.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    run(searchTpdb);
  }
});
elements.creatorFilter.addEventListener("input", () => renderPosters(state.posters));
elements.searchTpdb.addEventListener("click", () => run(searchTpdb));

run(loadConfig);
