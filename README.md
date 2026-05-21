# TPDb Plex Poster Picker

A local web app for choosing posters from The Poster Database and applying them to Plex movie and TV libraries.

The app connects to Plex, lists movie and show libraries, searches public TPDb pages for poster choices, and can either set a selected poster directly in Plex or save it into the item folder as `poster.jpg`. TV shows can also expand into seasons so each season can receive its own poster.

## Important TPDb note

The Poster Database does not currently expose a supported public search API. This app uses public TPDb pages and image endpoints, so TPDb layout changes can break search or poster extraction. Keep usage personal and reasonable.

## Run

```bash
python3 server.py
```

Open:

```text
http://127.0.0.1:8765
```

To use another port:

```bash
PORT=9000 python3 server.py
```

## Configure

In the app sidebar:

- `Plex URL`: usually `http://127.0.0.1:32400` if this runs on the Plex server.
- `Plex token`: your Plex authentication token.
- `Path mapping`: optional, one mapping per line, using `=>`.

Example path mapping:

```text
/data/media => /Volumes/Media
```

Use mappings when Plex reports media paths that differ from the paths visible to this app. If Plex runs in Docker, this is commonly required.

## Apply targets

The poster browser includes an apply target selector:

- `Set directly in Plex` uploads the selected image to Plex for that movie, show, or season. This does not require the app to reach your media folders.
- `Save local poster file` writes a local asset beside the media and refreshes that Plex item. This requires a local or mapped path the app can write to.

## Local poster filenames

In local poster mode, the app writes selected posters as:

```text
poster.jpg
```

or `poster.png` / `poster.webp` if TPDb serves that format.

For typical Plex local assets:

- Movies: saves beside the movie file.
- Shows: saves in the show folder exposed by Plex.
- Seasons: saves in the season folder, based on the first episode file Plex exposes.

If Plex does not expose an episode path for a season, the app falls back to `Season 01`, `Season 02`, and so on under the show folder.

## Plex token

Plex documents several ways to find your token, including from an authenticated Plex Web request. Treat it like a password because it grants access to your server.
