import os
import time
from flask import session
import spotipy
import logging
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
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
        self.sp_oauth = None
        redirect = os.getenv("SPOTIPY_REDIRECT_URI")

        self._oauth_config = {
            'client_id': os.getenv("SPOTIPY_CLIENT_ID"),
            'client_secret': os.getenv("SPOTIPY_CLIENT_SECRET"),
            'redirect_uri': redirect,
            'scope': self.scope,
            'cache_path': None,
        }

    def _ensure_token(self):
        self._ensure_oauth()
        token_info = session.get("token_info")
        if not token_info:
            return None
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
        self._ensure_oauth()
        try:
            token_info = self.sp_oauth.get_access_token(code)
        except SpotifyOauthError as e:
            logger = logging.getLogger(__name__)
            logger.warning("Spotify OAuth error during token exchange: %s", e)
            try:
                session['oauth_error'] = str(e)
            except Exception:
                pass
            return None
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception("Unexpected error during Spotify token exchange: %s", e)
            return None
        if hasattr(token_info, "get"):
            session["token_info"] = token_info
        else:
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
        playlists.sort(key=lambda p: (p.get('name') or '').lower())
        return playlists

    def get_user_playlists(self, user_id):
        """Return public playlists for the given user id as a list of dicts.
        Each dict contains id, name, tracks, and (optional) description.
        """
        if not self._ensure_token():
            return []
        playlists = []
        try:
            results = self.sp.user_playlists(user_id, limit=50)
        except Exception:
            return []
        while results:
            for p in results.get('items', []):
                playlists.append({
                    'id': p['id'],
                    'name': p['name'],
                    'tracks': p['tracks']['total'],
                    'images': p.get('images', []),
                })
            if results.get('next'):
                results = self.sp.next(results)
            else:
                break
        return playlists

    def get_user_profile(self, user_id):
        """Return minimal profile info for the given user id: display_name and avatar url (or None)."""
        if not self._ensure_token():
            return {'id': user_id, 'display_name': user_id, 'avatar': None}
        try:
            u = self.sp.user(user_id)
            name = u.get('display_name') or u.get('id') or user_id
            images = u.get('images') or []
            avatar = images[0]['url'] if images else None
            return {'id': user_id, 'display_name': name, 'avatar': avatar}
        except Exception:
            return {'id': user_id, 'display_name': user_id, 'avatar': None}

    def get_playlist(self, playlist_id):
        """Return raw playlist object for the given id, or None on failure."""
        if not self._ensure_token():
            return None
        try:
            return self.sp.playlist(playlist_id)
        except Exception:
            return None

    def create_playlist_from_tracks(self, name, track_uris, public=False):
        """Create a new playlist for the current user and add the given track URIs.
        Returns the created playlist object or None on failure.
        """
        if not self._ensure_token():
            return None
        try:
            user = self.sp.current_user()['id']
            playlist = self.sp.user_playlist_create(user, name, public=public)
            pid = playlist['id']
            for i in range(0, len(track_uris), 100):
                self.sp.playlist_add_items(pid, track_uris[i:i+100])
            # fetch fresh playlist object
            return self.sp.playlist(pid)
        except Exception:
            return None

    def update_liked_playlist(self, playlist_name="Liked songs as playlist"):
        """
        Create or replace a playlist with the user's saved (liked) songs.
        If a playlist with `playlist_name` exists, it will be overwritten.
        Returns the updated playlist object.
        """
        if not self._ensure_token():
            return None

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
        existing = None
        pls = self.get_playlists()
        for p in pls:
            if p.get('name') and p['name'].strip().lower() == playlist_name.strip().lower():
                existing = p['id']
                break

        if existing:
            pid = existing
            try:
                self.sp.playlist_replace_items(pid, [])
            except Exception:
                pid = self.sp.user_playlist_create(user, playlist_name, public=False)['id']
        else:
            pid = self.sp.user_playlist_create(user, playlist_name, public=False)['id']

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
                    tracks.append({
                        "id": t["id"],
                        "uri": t.get("uri"),
                        "name": t.get("name"),
                    })
            if results.get("next"):
                results = self.sp.next(results)
            else:
                break
        return tracks

    def get_playlist_tracks_meta(self, playlist_id):
        """Return track metadata for a playlist: id, uri, name, artists (string), album_image."""
        if not self._ensure_token():
            return []
        tracks = []
        results = self.sp.playlist_items(playlist_id, fields="items.track(id,uri,name,artists,album),next", limit=100)
        while results:
            for item in results.get('items', []):
                t = item.get('track')
                if not t or not t.get('id'):
                    continue
                artists = ', '.join([a.get('name') for a in (t.get('artists') or []) if a.get('name')])
                album = t.get('album') or {}
                images = album.get('images') or []
                album_img = images[0]['url'] if images else None
                tracks.append({
                    'id': t['id'],
                    'uri': t.get('uri'),
                    'name': t.get('name'),
                    'artists': artists,
                    'album_image': album_img,
                })
            if results.get('next'):
                results = self.sp.next(results)
            else:
                break
        return tracks

    def save_tracks_to_library(self, track_ids):
        """Save the given list of track IDs to the current user's library.
        Returns True on success.
        """
        if not self._ensure_token():
            return False
        try:
            # API accepts up to 50 ids per call
            for i in range(0, len(track_ids), 50):
                self.sp.current_user_saved_tracks_add(track_ids[i:i+50])
            return True
        except Exception:
            return False

    def get_saved_track_ids(self):
        """Return a set of track IDs that the current user has saved (liked).
        Useful for comparing another user's tracks against the current user's library.
        """
        if not self._ensure_token():
            return set()
        ids = []
        try:
            results = self.sp.current_user_saved_tracks(limit=50)
            while results:
                for item in results.get('items', []):
                    t = item.get('track')
                    if t and t.get('id'):
                        ids.append(t['id'])
                if results.get('next'):
                    results = self.sp.next(results)
                else:
                    break
        except Exception:
            return set()
        return set(ids)

    def get_saved_tracks_meta(self):
        """Return metadata for current user's saved tracks: list of dicts with id, name, artists (string), uri."""
        if not self._ensure_token():
            return []
        tracks = []
        try:
            results = self.sp.current_user_saved_tracks(limit=50)
            while results:
                for item in results.get('items', []):
                    t = item.get('track')
                    if not t or not t.get('id'):
                        continue
                    artists = ', '.join([a.get('name') for a in (t.get('artists') or []) if a.get('name')])
                    tracks.append({
                        'id': t.get('id'),
                        'uri': t.get('uri'),
                        'name': t.get('name'),
                        'artists': artists,
                    })
                if results.get('next'):
                    results = self.sp.next(results)
                else:
                    break
        except Exception:
            return []
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
        playlist = self.sp.user_playlist_create(user, new_name, public=False)
        pid = playlist["id"]
        for i in range(0, len(uris), 100):
            self.sp.playlist_add_items(pid, uris[i:i+100])
        return playlist

    def clean_out_playlist(self, playlist_id, new_name=None, overwrite_playlist_id=None, progress_cb=None):
        if not self._ensure_token():
            return None
        tracks = self._get_playlist_tracks(playlist_id)
        logger = logging.getLogger(__name__)
        logger.info("clean_out_playlist called for playlist_id=%s (tracks=%s) overwrite_target=%s", playlist_id, len(tracks), overwrite_playlist_id)
        # Build a set of track ids that are considered "saved" for the user.
        # This includes tracks in the user's liked songs AND tracks appearing in
        # any of the user's playlists (except the playlist being cleaned).
        saved_ids = set()
        try:
            saved_ids = set(self.get_saved_track_ids())
        except Exception:
            saved_ids = set()

        # Collect track ids from other user playlists (excluding the target playlist)
        try:
            user_playlists = self.get_playlists()
            for p in user_playlists:
                pid = p.get('id')
                # Skip the playlist being cleaned and also skip the playlist
                # that will be overwritten (if provided) so we don't treat it
                # as a saved source. Including the overwrite target would
                # incorrectly mark its tracks as "already saved" and produce
                # an empty cleaned result when updating in-place.
                if not pid or pid == playlist_id or (overwrite_playlist_id and pid == overwrite_playlist_id):
                    continue
                for t in self._get_playlist_tracks(pid):
                    tid = t.get('id')
                    if tid:
                        saved_ids.add(tid)
        except Exception:
            # If anything goes wrong here, we gracefully fall back to using
            # only the liked-songs set collected above.
            logger.exception('Failed to collect tracks from user playlists for saved_ids')
            pass

        # Keep URIs whose track id is NOT present in saved_ids
        keep_uris = []
        total_tracks = len(tracks)
        processed = 0
        for t in tracks:
            tid = t.get('id')
            if not tid or tid not in saved_ids:
                keep_uris.append(t.get('uri'))
            processed += 1
            # call progress callback if provided (processed, total)
            try:
                if progress_cb:
                    progress_cb(processed, total_tracks)
            except Exception:
                # never let progress reporting break the operation
                pass
        # If an existing playlist id is provided and the user requested
        # overwrite, replace its items. Otherwise create a new playlist
        # with the requested name.
        try:
            original_count = len(tracks)
            removed_count = original_count - len(keep_uris)
            logger.info("clean_out_playlist summary: original=%d saved_ids=%d keep=%d removed=%d", original_count, len(saved_ids), len(keep_uris), removed_count)

            if overwrite_playlist_id:
                # Replace items in the existing playlist
                try:
                    self.sp.playlist_replace_items(overwrite_playlist_id, [])
                except Exception:
                    # If replace fails, attempt to continue by adding items
                    pass
                for i in range(0, len(keep_uris), 100):
                    self.sp.playlist_add_items(overwrite_playlist_id, keep_uris[i:i+100])
                pl = self.sp.playlist(overwrite_playlist_id)
                return (pl, removed_count)

            name = new_name or f"Cleaned - {time.strftime('%Y-%m-%d %H:%M')}"
            user = self.sp.current_user()["id"]
            playlist = self.sp.user_playlist_create(user, name, public=False)
            pid = playlist["id"]
            for i in range(0, len(keep_uris), 100):
                self.sp.playlist_add_items(pid, keep_uris[i:i+100])
            pl = self.sp.playlist(pid)
            return (pl, removed_count)
        except Exception:
            return None

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
            playlist = self.sp.user_playlist_create(user, name, public=False)
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
