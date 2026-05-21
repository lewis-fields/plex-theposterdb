# TPDb Plex Poster Picker Context

## Purpose

This project is a local web app for choosing artwork from The Poster Database and applying it to a Plex library.

The user wants consistent movie and TV posters, often by the same TPDb creator. The app should:

- Connect to Plex using a Plex URL and token.
- List Plex movie and TV libraries.
- Show movie, TV show, and TV season items.
- Search TPDb for the matching title.
- Show TPDb poster choices and creator names.
- Apply selected posters either directly to Plex or as local `poster.*` assets.

## Current Repository State

The initial app was committed as:

```text
95672cc Build Plex TPDb poster picker
```

The repository remote is configured as:

```text
https://github.com/lewis-fields/plex-theposterdb.git
```

There are later uncommitted changes after the first commit. At the time this file was added they include:

- TV season support.
- Season-aware TPDb poster loading.
- Direct Plex artwork upload mode.
- Incremental TPDb pagination for faster default browsing.
- All-page creator filtering for the selected TPDb title.

## Files

- `server.py`: Python standard-library HTTP server, Plex API calls, TPDb page scraping, poster application.
- `static/index.html`: app structure.
- `static/app.js`: browser state and UI workflow.
- `static/styles.css`: UI styling.
- `README.md`: setup and user-facing notes.
- `config.json`: local runtime config, ignored by git.

## Runtime

Run locally with:

```bash
python3 server.py
```

Default URL:

```text
http://127.0.0.1:8765
```

The app stores Plex connection settings in ignored `config.json`.

## Plex Behavior

### Libraries and Items

The backend lists Plex movie and show libraries from:

```text
/library/sections
```

It lists items for a library from:

```text
/library/sections/{section}/all
```

Movies expose media-file paths. Shows expose show folder locations where Plex provides them.

### Seasons

Shows can expand into season rows.

The backend uses:

```text
/library/metadata/{showRatingKey}/children
```

to list seasons, then checks the first episode beneath each season to find the season folder. If Plex does not expose an episode path, it falls back to a `Season 01` style folder under the show folder.

### Apply Targets

The UI has an **Apply target** selector.

#### Set directly in Plex

This is the default. The chosen TPDb image is downloaded by the app and posted to Plex artwork storage for the selected Plex item.

Use this when the app cannot write to the media filesystem, for example when Plex runs on Windows and the app runs on a Mac.

#### Save local poster file

This writes:

```text
poster.jpg
```

or the served image format equivalent in the selected media folder, then refreshes that Plex item.

For Plex paths that are not locally writable, use path mappings such as:

```text
D:/Plex/Movies => /Volumes/Movies/Plex/Movies
E:/Plex/TV Shows => /Volumes/TV/Plex/TV Shows
E:/Plex/Movies => /Volumes/Movies2/Plex/Movies
```

The user's Plex example paths were:

```text
D:/Plex/Movies
E:/Plex/TV Shows
E:/Plex/Movies
```

## TPDb Behavior

## API Caveat

TPDb does not appear to expose a supported public search API for this workflow. The app scrapes public TPDb HTML pages and their image CDN URLs. Layout changes on TPDb may require scraper updates.

### Title Search

TPDb title search uses the public search page and chooses the movie or show search section.

The default UI fetches only the first TPDb search-result page for speed. If more title results exist, the UI shows:

```text
More title results
```

The backend can fetch up to six title search pages when requested incrementally.

### Poster Pages

The default UI loads the first poster page for the selected TPDb title. If more poster pages exist, the poster grid shows:

```text
Load more poster pages
```

The backend supports bounded page loading for normal poster browsing.

### Creator Filter

Creator filtering is intentionally deeper than ordinary browsing:

- Normal browsing remains incremental for speed.
- When a creator is typed into **Creator filter**, the UI waits briefly, then fetches all available poster pages for the selected TPDb title.
- The filter matches creator names only.

This was added because a creator's poster may be on a later TPDb page even if the initial poster page already rendered.

### TV Seasons on TPDb

TPDb show cover and season posters use the same show poster path with a season query parameter.

Examples:

```text
https://theposterdb.com/posters/7793
https://theposterdb.com/posters/7793?season=1
https://theposterdb.com/posters/7793?season=0
```

`season=0` represents specials. Season rows in the app use the selected Plex season index to build the TPDb season URL.

## UI Workflow

1. Configure Plex URL/token and optional path mappings.
2. Load Plex libraries.
3. Choose a movie or TV show.
4. For TV shows, season rows appear beneath the show after expansion.
5. Search TPDb.
6. Pick the matching TPDb title result.
7. Browse posters or use creator filter.
8. Choose apply target.
9. Apply the poster.

## Validation Already Used

Useful checks:

```bash
python3 -m py_compile server.py
node --check static/app.js
```

The app was also smoke-tested in a browser at `http://127.0.0.1:8765`.

Local smoke tests confirmed:

- Plex season discovery returns season folder targets.
- TPDb show-cover pages and `?season=1` pages return different poster sets.
- TPDb title search pagination can retrieve later search pages.
- All-page creator filtering finds creator matches beyond poster page 1.

## Known Constraints and Risks

- TPDb scraping is brittle by nature.
- Fetching many TPDb pages can be slow, so the default UI intentionally avoids eager deep pagination.
- Direct Plex upload changes live Plex metadata. Tests should avoid applying real posters unless that change is intended.
- Local file mode requires the app process to have a writable path to the media folder.
- `poster.jpg` may appear in the repo working directory during local tests; do not commit generated poster assets unless explicitly requested.

## Likely Next Work

- Commit and push the uncommitted TV season, apply-mode, pagination, and creator-filter work when the user asks.
- Add more explicit UI affordances for show versus season selection if season libraries become large.
- Consider a cache for TPDb search/poster pages to reduce repeat wait time.
- Consider creator autocomplete from loaded poster creators.
- Consider tests for TPDb HTML parsing using stored fixtures.
