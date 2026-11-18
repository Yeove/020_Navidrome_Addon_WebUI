# Navidrome Custom Frontend

A lightweight music player for your [Navidrome](https://www.navidrome.org) server, for desktop, phones, & tablets.

https://github.com/user-attachments/assets/d81f4ec9-cfd5-476b-9c85-39c952e08200

| File | What it is |
| --- | --- |
| `music.yeove.com/index.html` | The whole player. |
| `music.yeove.com/tagd.py` | Optional: a small helper that writes moods into your music files |
| `compose.yaml` | A ready-made Docker setup: Navidrome, the player and the mood helper |

## Features

- Favourites view
- Categories view: Albums, artists, genres, & moods
- Uncategorized view: Makes it easy to find songs that need to be added to a playlist.
- Playlists: create, rename, delete, and add a song to several at once
- A Now Playing view with a drag n' drop reorderable queue, and lock-screen controls for phones and tablets (Supporting Android & Apple)
- Export any song or playlist as FLAC, and export all your playlists as .m3u8 files
- Optional mood editor that writes `MOOD` tags into your music files (tagd.py file)
- Search bars for everything!

## Install

There are two ways:

### Option 1: Just the page (you already have Navidrome)

1. Download [`index.html`](music.yeove.com/index.html) (use the download button at the top right of that page).
2. Open it in your browser. Drop it onto any web server you already run.
3. Sign in with your Navidrome's address (for example `192.168.1.10:4533`), and the username and password you use for Navidrome.

That's it. Mood editing needs Option 2.

### Option 2: Docker (Navidrome, the player and mood editing)

1. Download this repo: **Code › Download ZIP**, then unzip it.
2. Open `compose.yaml` in a text editor. Near the top, change `/path/to/your/music` to your music folder, and save.
3. Start it. From the unzipped folder, run `docker compose up -d`.
   <br>Using Dockge, Portainer or a NAS app instead? Paste `compose.yaml` into a new stack, and also change `./music.yeove.com` near the top to the full path of the `music.yeove.com` folder.
4. Open Navidrome at `http://<your server>:4533` and create your account. Your music shows up once Navidrome has scanned it, which can take a while for a big library.
5. Open the player at `http://<your server>:4534` and sign in with that account.

`<your server>` is the address of the computer running Docker, such as `192.168.1.10`, or `localhost` if it's the computer you're on.

## Settings

Open `music.yeove.com/index.html` in a text editor. The settings are at the top:

| Setting | What it does |
| --- | --- |
| `moodEditing` | `true` allows mood editing. **Edit Moods…** only shows up when `tagd.py` is running (Option 2). `false` turns it off |
| `musicFolder` | Navidrome's music folder (its `ND_MUSICFOLDER`), used for the paths in exported playlists. This setting is already correct if you set this up using Option 2. With your own Navidrome, it's `/music` unless you changed it |
| `navidromeLink` | Address of Navidrome's own interface, for the Open Navidrome button in Settings. When this field is empty, it will automatically hide this button from the user interface. |
| `title` | Browser tab title. When empty, it uses the page's address |

Save, then refresh the page.

## Mood editing

Navidrome can only read tags, so there's a custom script called `tagd.py`, which is a small helper file with write access to your music. Option 2 runs it for you.

**Edit Moods…** appears in each song's `⋯` menu. A Navidrome admin account is required to change tags, and the helper won't touch anything outside your music folder. Moods are written as `MOOD` tags like `Relaxed; Focus`.
<br> Always make sure to keep backups of your music folder if enabling this.

To turn mood editing off, set `moodEditing: false` at the top of `index.html`. To remove the helper completely, delete the `music-tags` section from `compose.yaml`.

## Behind a reverse proxy

Send everything for your domain to port 4534. With Caddy, for example:

```
music.example.com {
	reverse_proxy 127.0.0.1:4534
}
```

If the player is on an `https://` address, Navidrome needs one too when you use Option 1, because browsers block an `https://` page from reaching a plain `http://` server.

## Notes

- **FLAC export** converts in your browser, because Navidrome won't turn lossy files into a lossless format. Songs already in FLAC are saved untouched.
- **Playlists** made in the player live in Navidrome's database. Playlists Navidrome imports from `.m3u8` files are read-only here.
- **Plays** count toward Navidrome's play counts after half a song, or four minutes.
