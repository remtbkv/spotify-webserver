import os
import time
from flask import session
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
load_dotenv()


class SpotifyClient:
    def __init__(self):
        self.sp = None
        self.scope = (
            "user-library-read playlist-read-private playlist-read-collaborative "
            "playlist-modify-private playlist-modify-public user-library-modify "
            "user-read-playback-state user-read-recently-played user-read-currently-playing "
            "user-read-playback-position user-modify-playback-state"
        )

        # Delay creating SpotifyOAuth until it's needed. In serverless
        # environments creating it at import-time can register handlers or
        # otherwise interact with vendor code that causes shutdown errors.
        self.sp_oauth = None
        self._oauth_config = {
            'client_id': os.getenv("SPOTIPY_CLIENT_ID"),
            'client_secret': os.getenv("SPOTIPY_CLIENT_SECRET"),
            'redirect_uri': os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:9090/callback"),
            'scope': self.scope,
            'cache_path': None,
        }

    def _ensure_token(self):
        # Ensure OAuth helper exists before token ops
        self._ensure_oauth()
        token_info = session.get("token_info")
        if not token_info:
            return None
        # refresh token if expired
        if self.sp_oauth.is_token_expired(token_info):
            refreshed = self.sp_oauth.refresh_access_token(token_info.get("refresh_token"))
            # refresh_access_token returns a dict with new access_token and expires_at
            token_info.update(refreshed)
            session["token_info"] = token_info
        self.sp = spotipy.Spotify(auth=session["token_info"]["access_token"])
        return self.sp

    def get_authorize_url(self):
        self._ensure_oauth()
        return self.sp_oauth.get_authorize_url()

    def handle_callback(self, request_args):
        code = request_args.get("code")
        if not code:
            return None
        # exchange code for token
        # Note: different spotipy versions return either a dict or an oauth object; handle both
        self._ensure_oauth()
        token_info = self.sp_oauth.get_access_token(code)
        # ensure token_info is a dict
        if hasattr(token_info, "get"):
            session["token_info"] = token_info
        else:
            # fallback if returned value is different
            session["token_info"] = dict(token_info)
        self.sp = spotipy.Spotify(auth=session["token_info"]["access_token"]) 
        return self.sp


    def _ensure_oauth(self):
        """Create the SpotifyOAuth helper lazily."""
        if self.sp_oauth is None:
            cfg = self._oauth_config
            self.sp_oauth = SpotifyOAuth(
                client_id=cfg['client_id'],
                client_secret=cfg['client_secret'],
                redirect_uri=cfg['redirect_uri'],
                scope=cfg['scope'],
                cache_path=cfg['cache_path'],
            )

    def get_current_user(self):
        if not self._ensure_token():
            return None
        return self.sp.current_user()

    def get_playlists(self):
        if not self._ensure_token():
            return []
        playlists = []
        results = self.sp.current_user_playlists(limit=50)
        while results:
            for p in results.get("items", []):
                playlists.append({"id": p["id"], "name": p["name"], "tracks": p["tracks"]["total"]})
            if results.get("next"):
                results = self.sp.next(results)
            else:
                break
        # sort playlists alphabetically by name for consistent UI
        playlists.sort(key=lambda p: (p.get('name') or '').lower())
        return playlists

    def update_liked_playlist(self, playlist_name="Liked songs as playlist"):
        """
        Create or replace a playlist with the user's saved (liked) songs.
        If a playlist with `playlist_name` exists, it will be overwritten.
        Returns the updated playlist object.
        """
        if not self._ensure_token():
            return None

        # fetch all liked songs
        ids = []
        results = self.sp.current_user_saved_tracks(limit=50)
        while results:
            for item in results.get('items', []):
                track = item.get('track')
                if track and track.get('id'):
                    ids.append(track['id'])
            if results.get('next'):
                results = self.sp.next(results)
            else:
                break

        user = self.sp.current_user()['id']
        # find existing playlist with that name (only search user's playlists)
        existing = None
        pls = self.get_playlists()
        for p in pls:
            if p.get('name') and p['name'].strip().lower() == playlist_name.strip().lower():
                existing = p['id']
                break

        if existing:
            pid = existing
            # replace items
            try:
                self.sp.playlist_replace_items(pid, [])
            except Exception:
                # fallback: create new
                pid = self.sp.user_playlist_create(user, playlist_name, public=False)['id']
        else:
            pid = self.sp.user_playlist_create(user, playlist_name, public=False)['id']

        # add tracks in batches
        for i in range(0, len(ids), 100):
            self.sp.playlist_add_items(pid, ids[i:i+100])

        return self.sp.playlist(pid)

    def _get_playlist_tracks(self, playlist_id):
        if not self._ensure_token():
            return []
        tracks = []
        results = self.sp.playlist_items(playlist_id, fields="items.track.id,items.track.uri,items.track.name,next", limit=100)
        while results:
            for item in results.get("items", []):
                t = item.get("track")
                if t and t.get("id"):
                    tracks.append({"id": t["id"], "uri": t["uri"], "name": t.get("name")})
            if results.get("next"):
                results = self.sp.next(results)
            else:
                break
        return tracks

    def merge_playlists(self, playlist_ids, new_name="Merged Playlist"):
        if not self._ensure_token():
            return None
        seen = set()
        uris = []
        for pid in playlist_ids:
            for t in self._get_playlist_tracks(pid):
                if t["uri"] not in seen:
                    seen.add(t["uri"])
                    uris.append(t["uri"])
        user = self.sp.current_user()["id"]
        playlist = self.sp.user_playlist_create(user, new_name)
        pid = playlist["id"]
        for i in range(0, len(uris), 100):
            self.sp.playlist_add_items(pid, uris[i:i+100])
        return playlist

    def clean_out_playlist(self, playlist_id, new_name=None):
        if not self._ensure_token():
            return None
        tracks = self._get_playlist_tracks(playlist_id)
        keep_uris = []
        # check saved status in batches of 50
        for i in range(0, len(tracks), 50):
            ids = [t["id"] for t in tracks[i:i+50]]
            contains = self.sp.current_user_saved_tracks_contains(ids)
            for t, saved in zip(tracks[i:i+50], contains):
                if not saved:
                    keep_uris.append(t["uri"])
        name = new_name or f"Cleaned - {time.strftime('%Y-%m-%d %H:%M')}"
        user = self.sp.current_user()["id"]
        playlist = self.sp.user_playlist_create(user, name)
        pid = playlist["id"]
        for i in range(0, len(keep_uris), 100):
            self.sp.playlist_add_items(pid, keep_uris[i:i+100])
        return playlist

    def _get_current_track_id(self):
        cp = self.sp.currently_playing()
        if not cp or not cp.get("item"):
            return None
        return cp["item"]["id"]

    def save_queue(self, queue_uris=None, new_name=None):
        """
        If `queue_uris` is provided (list of spotify:track:... URIs), create a playlist from them.
        If `queue_uris` is None or empty, attempt to read the user's active player queue by
        temporarily muting and skipping through tracks (best-effort; depends on user's device).
        """
        if not self._ensure_token():
            return (None, 'no_token')

        # If explicit URIs provided, just create playlist from them
        if queue_uris:
            name = new_name or f"Saved Queue - {time.strftime('%Y-%m-%d %H:%M')}"
            user = self.sp.current_user()["id"]
            playlist = self.sp.user_playlist_create(user, name)
            pid = playlist["id"]
            for i in range(0, len(queue_uris), 100):
                self.sp.playlist_add_items(pid, queue_uris[i:i+100])
            return (playlist, None)

        # Automated queue-reading flow
        SPOTIFY_QUEUE_LIMIT = 100
        DUMMY_ID = "6sVK7RXMHRGxAefiqEGEbP"
        DUMMY_URI = f"spotify:track:{DUMMY_ID}"

        cp = self.sp.current_playback()
        if not cp:
            return (None, 'no_playback')

        position = cp.get("progress_ms", 0)
        if not cp.get("is_playing"):
            try:
                self.sp.start_playback()
            except Exception:
                pass

        muted = False
        try:
            volume = cp["device"]["volume_percent"]
            try:
                self.sp.volume(0)
                muted = True
            except Exception:
                muted = False
        except Exception:
            muted = False

        try:
            current_id = self._get_current_track_id()
            if not current_id:
                if muted:
                    try:
                        self.sp.volume(volume)
                    except Exception:
                        pass
                return (None, 'no_current_track')

            self.sp.add_to_queue(DUMMY_URI)
            self.sp.add_to_queue(f"spotify:track:{current_id}")
            self.sp.next_track()
            time.sleep(0.25)

            q = []
            curr = self._get_current_track_id()
            n = 0
            while curr and curr != DUMMY_ID and n < SPOTIFY_QUEUE_LIMIT:
                q.append(f"spotify:track:{curr}")
                self.sp.next_track()
                time.sleep(0.25)
                next_id = curr
                start = time.time()
                while next_id == curr:
                    next_id = self._get_current_track_id()
                    time.sleep(0.1)
                    if time.time() - start > 1.25:
                        try:
                            self.sp.next_track()
                        except Exception:
                            pass
                        start = time.time()
                curr = next_id
                n += 1

            try:
                self.sp.next_track()
            except Exception:
                pass
            time.sleep(0.25)
            try:
                self.sp.seek_track(position)
            except Exception:
                pass

            if muted:
                try:
                    self.sp.volume(volume)
                except Exception:
                    pass

            if not q:
                return (None, 'empty')

            name = new_name or f"Saved Queue - {time.strftime('%Y-%m-%d %H:%M')}"
            user = self.sp.current_user()["id"]
            playlist = self.sp.user_playlist_create(user, name, public=False)
            pid = playlist["id"]
            for i in range(0, len(q), 100):
                self.sp.playlist_add_items(pid, q[i:i+100])
            return (playlist, None)
        except Exception:
            try:
                if muted:
                    self.sp.volume(volume)
            except Exception:
                pass
            return (None, 'error')
