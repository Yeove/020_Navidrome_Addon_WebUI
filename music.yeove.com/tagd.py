#!/usr/bin/env python3
"""music-tags: writes MOOD tags into your music files for Navidrome Custom Frontend.

Navidrome only reads tags, so this small helper is the one piece with write
access to the music folder. The page calls it at /tags/ (Caddy routes that
here). Every request carries the caller's Navidrome sign-in, which is checked
against Navidrome itself: only Navidrome admins can change tags, and only
files inside MUSIC_ROOT can be touched.

Moods are written the way the Essentia tagger writes them: one MOOD value
holding "a; b; c". Navidrome splits that into separate moods.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import mutagen
from mutagen.id3 import ID3, TXXX
from mutagen.mp4 import MP4, MP4FreeForm

NAVIDROME = os.environ.get("NAVIDROME_URL", "http://navidrome:4533").rstrip("/")
ROOT = os.path.realpath(os.environ.get("MUSIC_ROOT", "/music"))
PORT = int(os.environ.get("PORT", "8000"))
CLIENT = "navidrome-custom-frontend-tags"
WRITE = threading.Lock()  # one file write at a time
MP4_MOOD = "----:com.apple.iTunes:MOOD"


class Fail(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def navidrome(method, auth, **params):
    query = dict(auth, c=CLIENT, f="json", **params)
    url = f"{NAVIDROME}/rest/{method}?" + urllib.parse.urlencode(query, doseq=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)["subsonic-response"]
    except (urllib.error.URLError, ValueError, KeyError) as e:
        raise Fail(502, f"Couldn't reach Navidrome at {NAVIDROME} ({e}).")
    if data.get("status") != "ok":
        err = data.get("error", {})
        raise Fail(403 if err.get("code") in (40, 41, 50) else 502, err.get("message", "Navidrome refused the request."))
    return data


def unique(values):
    seen, out = set(), []
    for v in values:
        if v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def split(values):
    return unique([p.strip() for v in values for p in str(v).split(";") if p.strip()])


def read_moods(audio):
    tags = audio.tags
    if tags is None:
        return []
    if isinstance(tags, ID3):
        return split([t for frame in tags.getall("TXXX:MOOD") + tags.getall("TMOO") for t in frame.text])
    if isinstance(audio, MP4):
        return split([bytes(v).decode("utf-8", "replace") for v in tags.get(MP4_MOOD, [])])
    return split(tags.get("mood", []))  # Vorbis comments: FLAC, Opus, Ogg


def write_moods(audio, moods):
    if audio.tags is None:
        audio.add_tags()
    tags, text = audio.tags, "; ".join(moods)
    if isinstance(tags, ID3):
        tags.delall("TXXX:MOOD")
        tags.delall("TMOO")
        if moods:
            tags.add(TXXX(encoding=3, desc="MOOD", text=[text]))
    elif isinstance(audio, MP4):
        if moods:
            tags[MP4_MOOD] = [MP4FreeForm(text.encode("utf-8"))]
        elif MP4_MOOD in tags:
            del tags[MP4_MOOD]
    else:
        if moods:
            tags["MOOD"] = [text]
        elif "mood" in tags:
            del tags["mood"]
    audio.save()


def song_file(auth, song_id):
    path = navidrome("getSong", auth, id=song_id)["song"].get("path", "")
    if not path.startswith("/"):
        raise Fail(409, "Navidrome is giving the tag helper made-up file paths. Add ND_SUBSONIC_DEFAULTREPORTREALPATH=true "
                        f"to Navidrome, or turn on Report Real Path for the “{CLIENT}” player in Navidrome’s Players page.")
    real = os.path.realpath(path)
    if not real.startswith(ROOT + os.sep):
        raise Fail(403, f"That file is outside the music folder ({ROOT}), so it won't be changed.")
    if not os.path.isfile(real):
        raise Fail(404, "The file isn't where Navidrome says it is. Try a library scan first.")
    return real


def change_moods(auth, ids, add, remove):
    user = auth.get("u", "")
    if not user or not navidrome("getUser", auth, username=user)["user"].get("adminRole"):
        raise Fail(403, "Only Navidrome admins can change tags.")
    add, remove = split(add), {m.lower() for m in split(remove)}
    result = {}
    for song_id in ids:
        path = song_file(auth, song_id)
        with WRITE:
            audio = mutagen.File(path)
            if audio is None:
                raise Fail(415, f"Can't write tags to {os.path.basename(path)}.")
            moods = [m for m in read_moods(audio) if m.lower() not in remove]
            have = {m.lower() for m in moods}
            moods += [m for m in add if m.lower() not in have]
            write_moods(audio, moods)
            result[song_id] = read_moods(mutagen.File(path))
    request_rescan(auth)
    return result


# Navidrome ignores a scan request while one is running, so edits made during
# a scan could wait for the next scheduled one. Instead, one follow-up scan is
# queued after the last edit, once any running scan has finished.
_pending = {"auth": None}
_wake = threading.Condition()


def request_rescan(auth):
    with _wake:
        _pending["auth"] = auth
        _wake.notify()


def rescanner():
    while True:
        with _wake:
            while not _pending["auth"]:
                _wake.wait()
            auth, _pending["auth"] = _pending["auth"], None
        time.sleep(1.5)  # quick successive edits share one scan
        for _ in range(120):
            try:
                if not navidrome("getScanStatus", auth)["scanStatus"].get("scanning"):
                    break
            except Fail:
                break
            time.sleep(1)
        try:
            navidrome("startScan", auth)
        except Fail as e:
            print(f"rescan failed: {e}", flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "music-tags/1"

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def route(self):
        url = urllib.parse.urlsplit(self.path)
        return url.path.removeprefix("/tags").rstrip("/") or "/", urllib.parse.parse_qs(url.query)

    def do_GET(self):
        path, _ = self.route()
        if path in ("/", "/health"):
            self.reply(200, {"ok": True, "root": ROOT})
        else:
            self.reply(404, {"ok": False, "error": "Not found."})

    def do_POST(self):
        path, query = self.route()
        if path != "/moods":
            return self.reply(404, {"ok": False, "error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                raise Fail(413, "Request too large.")
            body = json.loads(self.rfile.read(length) or b"{}")
            auth = {k: query[k][0] for k in ("u", "t", "s", "v") if k in query}
            ids = [str(i) for i in body.get("ids", [])][:500]
            if not ids:
                raise Fail(400, "No songs given.")
            songs = change_moods(auth, ids, body.get("add", []), body.get("remove", []))
            self.reply(200, {"ok": True, "songs": songs})
        except Fail as e:
            self.reply(e.status, {"ok": False, "error": str(e)})
        except Exception as e:  # keep the helper up whatever happens
            self.reply(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    threading.Thread(target=rescanner, daemon=True).start()
    print(f"music-tags on :{PORT}, writing under {ROOT}, Navidrome at {NAVIDROME}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
