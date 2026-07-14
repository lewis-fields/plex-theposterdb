# TPDb Plex Poster Picker

A local web app for choosing posters from The Poster Database and applying them to Plex movie and TV libraries.

The app connects to Plex, lists movie and show libraries, searches public TPDb pages for poster choices, and can either set a selected poster directly in Plex or save it into the item folder. Movies and shows use `poster.ext`; TV shows can also expand into seasons so each season can receive its own Plex-named poster.

## Important TPDb note

The Poster Database does not currently expose a supported public search API. This app uses public TPDb pages and image endpoints, so TPDb layout changes can break search or poster extraction. Keep usage personal and reasonable.

## Run

Install Python dependencies first:

```bash
python3 -m pip install -r requirements.txt
```

The app currently has no third-party runtime dependencies, so this keeps setup ready for future packages without installing anything extra.

Start the app:

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

## Docker and Unraid

The repository publishes `linux/amd64` and `linux/arm64` images to GitHub
Container Registry. Start the included Compose stack with:

```bash
docker compose up -d
```

Open `http://localhost:8765`. The app runs as an unprivileged user and stores its
configuration in the persistent `poster-picker-config` volume. Compose publishes
the port on the host's loopback interface by default because the app has no login
screen and its saved Plex token is available to the web UI. To deliberately make
it reachable from your network, set `BIND_ADDRESS=0.0.0.0` in a `.env` file and
consider putting it behind an authenticated reverse proxy. Set `APP_PORT` there
if the host port needs to be something other than `8765`.

### Unraid setup

Example `compose.yaml` for the Unraid Compose Manager plugin:

```yaml
services:
  poster-picker:
    image: ghcr.io/lewis-fields/plex-theposterdb:latest
    container_name: plex-theposterdb
    pull_policy: always
    restart: unless-stopped
    environment:
      PUID: "99"
      PGID: "100"
    ports:
      - "8765:8765"
    volumes:
      - /mnt/user/appdata/plex-theposterdb:/config
      # These media mounts are only needed for "Save local poster file".
      # Change the host paths to match your Unraid shares.
      - /mnt/user/media/movies:/media/movies
      - /mnt/user/media/tv:/media/tv
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

After starting the stack, open `http://UNRAID-IP:8765`. If Plex uses host
networking, configure its URL as `http://host.docker.internal:32400`. If Plex and
this app share a custom Docker network, use the Plex container name instead,
such as `http://plex:32400`.

The example media mounts expose the Unraid shares at `/media/movies` and
`/media/tv` inside this container. Add matching path mappings in the app when
Plex reports different paths, or remove both mounts if you only upload posters
directly to Plex.

In **Docker > Add Container**, switch to advanced view and configure:

- **Repository:** `ghcr.io/lewis-fields/plex-theposterdb:latest`
- **Network Type:** `Bridge`
- **Web UI port:** container `8765`, with any available host port
- **Appdata path:** `/mnt/user/appdata/plex-theposterdb` mapped to `/config`
- **PUID:** `99`
- **PGID:** `100`

Add each media share as another read/write path only if you want the app to save
poster files beside the media. Direct uploads to Plex do not need media paths.
For example, map `/mnt/user/media/movies` to `/media/movies`, then configure the
corresponding Plex-to-container path mapping in the app.

The GHCR package is public, so Unraid can pull it without registry credentials.
Pushes to `main` update `latest`, and tags such as `v1.2.0` also publish `1.2.0`
and `1.2` image tags.

If Plex is another container, attach this service to the same Docker network and
use the Plex service name for the Plex URL, for example `http://plex:32400`. If
Plex runs on the Docker host, use `http://host.docker.internal:32400` on Docker
Desktop. Linux Docker Engine deployments may also need this service setting:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Direct Plex uploads need no media mounts. To use **Save local poster file**, add
the relevant media folders to `compose.yaml` and configure matching path mappings
in the app:

```yaml
services:
  poster-picker:
    volumes:
      - poster-picker-config:/config
      - /srv/media/movies:/media/movies
      - /srv/media/tv:/media/tv
```

For example, if Plex reports `/data/movies` but the mount above exposes the same
files at `/media/movies`, add this mapping in the sidebar:

```text
/data/movies => /media/movies
```

The container drops privileges before starting. `PUID` and `PGID` control its
runtime identity; use `99` and `100` on Unraid so it can use standard shares. The
following environment variables are supported:

- `HOST`: listen address (image default: `0.0.0.0`; local default: `127.0.0.1`)
- `PORT`: HTTP port (default: `8765`)
- `CONFIG_PATH`: configuration file path (image default: `/config/config.json`)
- `PUID`: runtime user ID (default: `10001`; use `99` on Unraid)
- `PGID`: runtime group ID (default: `10001`; use `100` on Unraid)

## Configure

In the app sidebar:

- `Plex URL`: usually `http://127.0.0.1:32400` if this runs on the Plex server.
- `Plex token`: your Plex authentication token.
- `Path mappings`: optional, one mapping per line, using `=>`.
- `Remove Kometa Overlay label after applying posters`: optional. When enabled, poster applies also remove Plex's `Overlay` label from the selected movie, show, or season.

Example path mappings:

```text
D:\Plex\Movies => W:\Plex\Movies
E:\Plex\TV Shows => W:\Plex\TV Shows
```

Use mappings when Plex reports media paths that differ from the paths visible to this app. Each Plex library root can have its own absolute mapping. If Plex runs in Docker, this is commonly required.

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

When a saved poster changes extension, the app removes older local poster files for the same Plex asset name first, such as replacing an old `poster.jpg` with a new `poster.png`.

For typical Plex local assets:

- Movies: saves beside the movie file.
- Shows: saves in the show folder exposed by Plex.
- Seasons: saves in the season folder, based on the first episode file Plex exposes. Numbered seasons use `season01`, `season02`, and so on; Specials uses `season-specials-poster`.

If Plex does not expose an episode path for a season, the app falls back to `Season 01`, `Season 02`, and so on under the show folder.

## Plex token

Plex documents several ways to find your token, including from an authenticated Plex Web request. Treat it like a password because it grants access to your server.
