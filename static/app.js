const maxSearchPageLimit = 6;
const maxPosterPageLimit = 12;

const state = {
  libraries: [],
  items: [],
  seasonsByShow: {},
  loadingSeasons: new Set(),
  posters: [],
  selectedItem: null,
  selectedTargetUrl: "",
  selectedTargetBaseUrl: "",
  searchPageLimit: 1,
  posterPageLimit: 1,
  posterHasMore: false,
  allPosterPagesLoaded: false,
  applyMode: localStorage.getItem("applyMode") || "plex",
  busy: false,
};
let creatorFilterTimer;

const elements = {
  configForm: document.querySelector("#configForm"),
  plexUrl: document.querySelector("#plexUrl"),
  plexToken: document.querySelector("#plexToken"),
  pathMappings: document.querySelector("#pathMappings"),
  removeOverlayLabelOnApply: document.querySelector("#removeOverlayLabelOnApply"),
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
  tpdbYearFilter: document.querySelector("#tpdbYearFilter"),
  applyMode: document.querySelector("#applyMode"),
  creatorFilter: document.querySelector("#creatorFilter"),
  targetList: document.querySelector("#targetList"),
  posterGrid: document.querySelector("#posterGrid"),
  posterActions: document.querySelector("#posterActions"),
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
  elements.tpdbYearFilter.disabled = !state.selectedItem;
  elements.creatorFilter.disabled = state.posters.length === 0;
}

function setApplyMode(mode) {
  state.applyMode = mode === "local" ? "local" : "plex";
  elements.applyMode.value = state.applyMode;
  localStorage.setItem("applyMode", state.applyMode);
  if (state.posters.length) {
    renderPosters(state.posters, state.posterHasMore && state.posterPageLimit < maxPosterPageLimit);
  }
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
  elements.removeOverlayLabelOnApply.checked = Boolean(config.remove_overlay_label_on_apply);
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
      remove_overlay_label_on_apply: elements.removeOverlayLabelOnApply.checked,
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
    const payload = await api(
      `/api/seasons?show=${encodeURIComponent(show.ratingKey)}&section=${encodeURIComponent(show.sectionKey || "")}`,
    );
    state.seasonsByShow[show.ratingKey] = payload.seasons;
    if (payload.showFolder && !show.file) {
      show.file = payload.showFolder;
      if (state.selectedItem?.ratingKey === show.ratingKey) {
        elements.selectedMeta.textContent = selectedItemMeta(state.selectedItem);
      }
    }
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
  state.selectedTargetBaseUrl = "";
  state.searchPageLimit = 1;
  state.posterPageLimit = 1;
  state.posterHasMore = false;
  state.allPosterPagesLoaded = false;
  state.posters = [];
  const displayTitle = item.type === "season" ? `${item.parentTitle} · ${item.title}` : `${item.title}${item.year ? ` (${item.year})` : ""}`;
  elements.selectedTitle.textContent = displayTitle;
  elements.selectedMeta.textContent = selectedItemMeta(item);
  elements.tpdbSearchTerm.value = item.searchTitle || item.parentTitle || item.title;
  elements.tpdbYearFilter.value = item.year || "";
  elements.creatorFilter.value = "";
  elements.searchTpdb.disabled = false;
  elements.tpdbSearchTerm.disabled = false;
  elements.tpdbYearFilter.disabled = false;
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
  elements.posterActions.innerHTML = "";
  const term = elements.tpdbSearchTerm.value.trim() || state.selectedItem.title;
  const payload = await api(
    `/api/tpdb/search?term=${encodeURIComponent(term)}&type=${encodeURIComponent(state.selectedItem.type)}&maxPages=${state.searchPageLimit}`,
  );
  const targets = yearFilteredTargets(payload.targets);
  renderTargets(targets, payload.hasMore && state.searchPageLimit < maxSearchPageLimit);
  if (!targets.length) {
    const year = activeYearFilter();
    const moreText = payload.hasMore ? " Load more title results to search deeper." : "";
    setStatus(year ? `No TPDb title results matched ${year} in the loaded results.${moreText}` : "No TPDb search results found.");
    return;
  }
  const searchPageText = `${payload.pagesFetched || 1} search page${payload.pagesFetched === 1 ? "" : "s"}`;
  const moreText = payload.hasMore ? " Load more title results to search deeper." : "";
  const yearText = activeYearFilter() ? ` matching ${activeYearFilter()}` : "";
  setStatus(`${targets.length} TPDb title result${targets.length === 1 ? "" : "s"}${yearText} found across ${searchPageText}.${moreText}`);
  if (targets.length === 1) {
    await loadPosters(targets[0].url, elements.targetList.querySelector(".target"), 1);
    return;
  }
  elements.posterGrid.innerHTML = '<div class="emptyState">Choose the matching TPDb title result to load posters.</div>';
}

async function loadMoreTargets() {
  if (!state.selectedItem) return;
  state.searchPageLimit = Math.min(state.searchPageLimit + 1, maxSearchPageLimit);
  setStatus("Loading more TPDb title results...");
  const term = elements.tpdbSearchTerm.value.trim() || state.selectedItem.title;
  const payload = await api(
    `/api/tpdb/search?term=${encodeURIComponent(term)}&type=${encodeURIComponent(state.selectedItem.type)}&maxPages=${state.searchPageLimit}`,
  );
  const targets = yearFilteredTargets(payload.targets);
  renderTargets(targets, payload.hasMore && state.searchPageLimit < maxSearchPageLimit);
  const moreText = payload.hasMore ? " More title results are still available." : "";
  const yearText = activeYearFilter() ? ` matching ${activeYearFilter()}` : "";
  setStatus(`${targets.length} TPDb title result${targets.length === 1 ? "" : "s"}${yearText} loaded from ${payload.pagesFetched} search pages.${moreText}`);
}

function renderTargets(targets, hasMore = false) {
  elements.targetList.innerHTML = "";
  if (!targets.length) {
    elements.posterGrid.innerHTML = `<div class="emptyState">${activeYearFilter() ? "No TPDb result matched that title and year." : "No TPDb result matched this title."}</div>`;
  }
  for (const target of targets) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "target";
    button.textContent = target.title;
    button.title = target.title;
    button.classList.toggle("active", state.selectedTargetBaseUrl === target.url);
    button.addEventListener("click", () => run(() => loadPosters(target.url, button, 1)));
    elements.targetList.append(button);
  }
  if (hasMore) {
    const moreButton = document.createElement("button");
    moreButton.type = "button";
    moreButton.className = "target more";
    moreButton.textContent = "More title results";
    moreButton.addEventListener("click", () => run(loadMoreTargets));
    elements.targetList.append(moreButton);
  }
}

function activeYearFilter() {
  const year = elements.tpdbYearFilter.value.trim();
  return /^\d{4}$/.test(year) ? year : "";
}

function yearFilteredTargets(targets) {
  const year = activeYearFilter();
  if (!year) return targets;
  return targets.filter((target) => target.year === year || target.title.includes(`(${year})`));
}

async function loadPosters(url, activeButton, pageLimit = state.posterPageLimit) {
  const posterUrl = posterUrlForSelection(url);
  const previousPosterCount = state.posters.length;
  const isLoadingMore = pageLimit > state.posterPageLimit && previousPosterCount > 0;
  state.selectedTargetBaseUrl = url;
  state.selectedTargetUrl = posterUrl;
  state.posterPageLimit = Math.min(pageLimit, maxPosterPageLimit);
  for (const button of elements.targetList.querySelectorAll(".target")) {
    button.classList.toggle("active", button === activeButton);
  }
  const loadingLabel = state.selectedItem?.type === "season" ? "Loading season poster pages" : "Loading poster pages";
  setStatus(loadingLabel + "...");
  elements.posterGrid.innerHTML = loadingMarkup(loadingLabel);
  elements.posterActions.innerHTML = "";
  const payload = await api(`/api/tpdb/posters?url=${encodeURIComponent(posterUrl)}&maxPages=${state.posterPageLimit}`);
  state.posters = payload.posters;
  state.posterHasMore = payload.hasMore;
  state.allPosterPagesLoaded = !payload.hasMore;
  elements.creatorFilter.disabled = state.posters.length === 0;
  renderPosters(payload.posters, payload.hasMore && state.posterPageLimit < maxPosterPageLimit);
  if (isLoadingMore) {
    alignFirstNewPoster(previousPosterCount);
  }
  if (!payload.posters.length) {
    setStatus("No posters found on that TPDb page.");
    return;
  }
  const pageText = `${payload.pagesFetched || 1} TPDb page${payload.pagesFetched === 1 ? "" : "s"}`;
  const moreText = payload.hasMore ? " Load more poster pages to continue." : "";
  const scopeText = state.selectedItem?.type === "season" ? "season posters" : "posters";
  setStatus(`${payload.posters.length} ${scopeText} found across ${pageText}.${moreText}`);
}

async function loadAllPostersForCreator() {
  if (!state.selectedTargetUrl || state.allPosterPagesLoaded) {
    renderPosters(state.posters, state.posterHasMore && state.posterPageLimit < maxPosterPageLimit);
    return;
  }
  const creator = elements.creatorFilter.value.trim();
  if (!creator) {
    renderPosters(state.posters, state.posterHasMore && state.posterPageLimit < maxPosterPageLimit);
    return;
  }
  setStatus(`Searching all TPDb poster pages for ${creator}...`);
  elements.posterGrid.innerHTML = loadingMarkup("Searching all poster pages");
  elements.posterActions.innerHTML = "";
  const payload = await api(`/api/tpdb/posters?url=${encodeURIComponent(state.selectedTargetUrl)}&allPages=1`);
  state.posters = payload.posters;
  state.posterHasMore = payload.hasMore;
  state.allPosterPagesLoaded = !payload.hasMore;
  state.posterPageLimit = Math.max(state.posterPageLimit, payload.pagesFetched || state.posterPageLimit);
  renderPosters(state.posters, false);
  const matches = visiblePostersForCreator(state.posters).length;
  setStatus(`${matches} posters by matching creators found across ${payload.pagesFetched} TPDb poster pages.`);
}

function posterUrlForSelection(url) {
  if (state.selectedItem?.type !== "season") {
    return url;
  }
  const posterUrl = new URL(url);
  posterUrl.searchParams.set("season", state.selectedItem.index || "0");
  return posterUrl.toString();
}

function renderPosters(posters, hasMore = false) {
  const visiblePosters = visiblePostersForCreator(posters);

  elements.posterGrid.innerHTML = "";
  elements.posterActions.innerHTML = "";
  elements.posterGrid.classList.toggle("empty", visiblePosters.length === 0);
  if (!visiblePosters.length) {
    elements.posterGrid.innerHTML = `<div class="emptyState">${posters.length ? "No posters match that creator." : "No poster assets were visible on this page."}</div>`;
    return;
  }
  for (const poster of visiblePosters) {
    const card = document.createElement("article");
    card.className = "posterCard";
    const previewUrl = poster.previewUrl || poster.imageUrl;
    const proxiedImage = `/api/proxy-image?url=${encodeURIComponent(previewUrl)}`;
    card.innerHTML = `
      <img src="${proxiedImage}" alt="${escapeHtml(poster.title)}" loading="lazy" />
      <div class="posterInfo">
        <strong title="${escapeHtml(poster.creator || poster.title)}">${escapeHtml(poster.creator || "Unknown creator")}</strong>
        <span title="${escapeHtml(poster.title)}">${escapeHtml(poster.title)}</span>
        <button class="apply" type="button">${state.applyMode === "plex" ? "Set in Plex" : "Save poster file"}</button>
      </div>
    `;
    card.querySelector(".apply").addEventListener("click", () => applyPoster(poster.imageUrl));
    elements.posterGrid.append(card);
  }
  if (hasMore && state.selectedTargetBaseUrl) {
    const moreButton = document.createElement("button");
    moreButton.type = "button";
    moreButton.className = "loadMore";
    moreButton.textContent = "Load more poster pages";
    moreButton.addEventListener("click", () => run(() => loadPosters(state.selectedTargetBaseUrl, activeTargetButton(), state.posterPageLimit + 1)));
    elements.posterActions.append(moreButton);
  }
}

function alignFirstNewPoster(previousPosterCount) {
  const cards = elements.posterGrid.querySelectorAll(".posterCard");
  const targetCard = cards[previousPosterCount];
  if (targetCard) {
    targetCard.scrollIntoView({ block: "start", behavior: "smooth" });
  }
}

function visiblePostersForCreator(posters) {
  const creatorFilter = elements.creatorFilter.value.trim().toLowerCase();
  if (!creatorFilter) return posters;
  return posters.filter((poster) => (poster.creator || "").toLowerCase().includes(creatorFilter));
}

function activeTargetButton() {
  return elements.targetList.querySelector(".target.active");
}

async function applyPoster(imageUrl) {
  if (!state.selectedItem) return;
  setStatus(state.applyMode === "plex" ? "Uploading poster to Plex..." : "Saving poster file and refreshing Plex...");
  const payload = await api("/api/apply", {
    method: "POST",
    body: JSON.stringify({ item: state.selectedItem, imageUrl, mode: state.applyMode }),
  });
  const posterStatus = payload.mode === "plex" ? "Poster set directly in Plex." : `Poster saved: ${payload.path}`;
  const overlayStatus = payload.overlayLabelRemoved ? " Kometa Overlay label removed." : "";
  const plexWarning = payload.plexUpdateError ? ` Plex update did not finish: ${payload.plexUpdateError}` : "";
  setStatus(posterStatus + overlayStatus + plexWarning, Boolean(payload.plexUpdateError));
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
  state.selectedTargetBaseUrl = "";
  state.searchPageLimit = 1;
  state.posterPageLimit = 1;
  state.posterHasMore = false;
  state.allPosterPagesLoaded = false;
  state.posters = [];
  elements.selectedTitle.textContent = "Select an item";
  elements.selectedMeta.textContent = "Choose a movie or show to begin.";
  elements.searchTpdb.disabled = true;
  elements.tpdbSearchTerm.value = "";
  elements.tpdbSearchTerm.disabled = true;
  elements.tpdbYearFilter.value = "";
  elements.tpdbYearFilter.disabled = true;
  elements.creatorFilter.value = "";
  elements.creatorFilter.disabled = true;
  elements.targetList.innerHTML = "";
  elements.posterGrid.innerHTML = '<div class="emptyState">Poster choices will appear here.</div>';
  elements.posterGrid.classList.add("empty");
  elements.posterActions.innerHTML = "";
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
elements.tpdbYearFilter.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    run(searchTpdb);
  }
});
elements.creatorFilter.addEventListener("input", () => {
  window.clearTimeout(creatorFilterTimer);
  renderPosters(state.posters, state.posterHasMore && state.posterPageLimit < maxPosterPageLimit);
  if (!elements.creatorFilter.value.trim() || !state.posterHasMore || state.allPosterPagesLoaded) {
    return;
  }
  creatorFilterTimer = window.setTimeout(() => run(loadAllPostersForCreator), 450);
});
elements.applyMode.addEventListener("change", () => setApplyMode(elements.applyMode.value));
elements.searchTpdb.addEventListener("click", () => run(searchTpdb));

setApplyMode(state.applyMode);
run(loadConfig);
