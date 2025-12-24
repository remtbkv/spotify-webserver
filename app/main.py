import os
import logging
import threading
import spotipy
import time
from functools import wraps
from uuid import uuid4
from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory, jsonify
from werkzeug.exceptions import HTTPException
from app.spotify_client import SpotifyClient


app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret-key')
app.logger.setLevel(logging.WARNING)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            user = client.get_current_user()
        except Exception:
            user = None
        if not user:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('index'))
        return fn(*args, **kwargs)
    return wrapper


client = SpotifyClient()

# In-memory store for generated compare results. Ephemeral: restart clears it.
GENERATED = {}
# In-memory progress store for background clean tasks
PROGRESS = {}


@app.context_processor
def inject_current_user():
    try:
        user = client.get_current_user()
    except Exception:
        user = None
    return {'current_user': user}


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        app.logger.info(f'HTTP exception during request: {error}')
        return error.description, error.code
    app.logger.exception('Unhandled exception during request')
    return 'Internal Server Error', 500


@app.before_request
def log_request_info():
    app.logger.info(f'Incoming request: {request.method} {request.path}')
    try:
        app.logger.info(f'session keys: {list(session.keys())}')
    except Exception:
        pass


@app.route('/favicon.ico')
def favicon():
    try:
        return send_from_directory(app.static_folder, 'favicon.ico')
    except Exception:
        return ('', 204)


@app.route("/")
def index():
    code = request.args.get('code')
    error = request.args.get('error')
    if error:
        flash(f"Spotify authorization error: {error}", "error")
        return render_template("index.html")
    if code:
        sp = client.handle_callback(request.args)
        if not sp:
            oauth_err = None
            try:
                oauth_err = session.pop('oauth_error', None)
            except Exception:
                oauth_err = None
            if oauth_err and 'invalid_client' in oauth_err.lower():
                flash("Authorization failed: invalid client credentials.", "error")
            else:
                flash("Authorization failed.", "error")
            return render_template("index.html")
        return redirect(url_for('playlists'))
    user = client.get_current_user()
    if user:
        return redirect(url_for('playlists'))
    return render_template("index.html")


@app.route('/login')
def login():
    return redirect(client.get_authorize_url())


@app.route('/callback')
def callback():
    sp = client.handle_callback(request.args)
    if not sp:
        oauth_err = None
        try:
            oauth_err = session.pop('oauth_error', None)
        except Exception:
            oauth_err = None
        if oauth_err:
            app.logger.warning('OAuth token exchange failed: %s', oauth_err)
            flash(f"Authorization failed: {oauth_err}", "error")
        else:
            app.logger.warning('OAuth token exchange failed: unknown reason')
            flash("Authorization failed.", "error")
        return redirect(url_for('index'))
    return redirect(url_for('playlists'))


@app.route('/playlists')
@login_required
def playlists():
    pls = client.get_playlists()
    user = client.get_current_user()
    compare_user = request.args.get('compare_user')
    compare_playlists = None
    if compare_user:
        # normalize an input that might be a URL or an id
        try:
            uid = compare_user.split('?')[0].split('/')[-1]
            up = client.get_user_playlists(uid)
            # for each playlist, include its tracks (meta)
            compare_playlists = []
            for p in up:
                tracks = client.get_playlist_tracks_meta(p['id'])
                compare_playlists.append({
                    'id': p['id'],
                    'name': p['name'],
                    'tracks_count': p.get('tracks', 0),
                    'images': p.get('images', []),
                    'tracks': tracks,
                })
        except Exception:
            compare_playlists = None
            flash('Unable to fetch user playlists. Make sure the user id or URL is correct and the playlists are public.', 'error')
    return render_template('playlists.html', playlists=pls, user=user, compare_playlists=compare_playlists, compare_user=compare_user)


@app.route('/compare_fetch', methods=['POST'])
@login_required
def compare_fetch():
    """AJAX endpoint: given a compare_user, compute per-playlist unique and
    similar tracks (artist+title logic) relative to the current user's saved
    tracks. Stores the full, unique and similar lists for each playlist and
    returns a short URL to view the comparison.
    """
    try:
        data = request.get_json() or request.form.to_dict() or {}
    except Exception:
        data = request.form.to_dict() or {}
    compare_user = (data.get('compare_user') or '').strip()
    if not compare_user:
        return jsonify({'ok': False, 'error': 'No user provided'}), 400

    try:
        uid = compare_user.split('?')[0].split('/')[-1]
        user_playlists = client.get_user_playlists(uid)

        # get saved tracks metadata for current user (liked songs)
        saved_meta = client.get_saved_tracks_meta() or []
        # also include *all* tracks from the user's own playlists
        all_playlist_tracks = []
        try:
            my_playlists = client.get_playlists() or []
            for myp in my_playlists:
                try:
                    tmeta = client.get_playlist_tracks_meta(myp['id'])
                except Exception:
                    tmeta = []
                all_playlist_tracks.extend(tmeta)
        except Exception:
            all_playlist_tracks = []

        from collections import Counter

        playlists_out = []
        total_matches = 0
        # For each playlist, compute unique vs similar using artist+title logic.
        # We follow the efficient approach from your PlaylistManager:
        #  - pl_tracks = tracks for this playlist
        #  - al_tracks = all my tracks (liked + other playlists) excluding this playlist
        #  - t_counts_pl, t_counts_al = Counter(titles in pl), Counter(titles in al)
        #  - potential_saved = intersection of title sets
        #  - seen = set of (artist, title) from al_tracks for titles in potential_saved
        #  - iterate pl_tracks, if (artist,title) in seen then it's already-saved, else unique and add to seen
        my_playlists = client.get_playlists() or []
        for p in user_playlists:
            try:
                tracks = client.get_playlist_tracks_meta(p['id'])
            except Exception:
                tracks = []

            # Build pl_tracks as list of dicts with primary artist separated
            pl_rows = []
            for t in tracks:
                title = (t.get('name') or '').strip()
                artists = (t.get('artists') or '').strip()
                primary = (artists.split(',')[0].strip()) if artists else ''
                pl_rows.append({
                    'id': t.get('id'),
                    'uri': t.get('uri'),
                    'name': title,
                    'artist': primary,
                    'artists': artists,
                    'album_image': t.get('album_image'),
                })

            # Build al_tracks: saved_meta (liked songs) + tracks from my playlists excluding this playlist
            al_rows = []
            if saved_meta:
                for s in saved_meta:
                    title = (s.get('name') or '').strip()
                    artists = (s.get('artists') or '').strip()
                    primary = (artists.split(',')[0].strip()) if artists else ''
                    al_rows.append((s.get('id'), primary, title))
            for myp in my_playlists:
                if myp.get('id') == p.get('id'):
                    continue
                try:
                    tmeta = client.get_playlist_tracks_meta(myp['id'])
                except Exception:
                    tmeta = []
                for s in tmeta:
                    title = (s.get('name') or '').strip()
                    artists = (s.get('artists') or '').strip()
                    primary = (artists.split(',')[0].strip()) if artists else ''
                    al_rows.append((s.get('id'), primary, title))

            # Counters by title
            t_counts_pl = Counter(t['name'] for t in pl_rows if t.get('name'))
            t_counts_al = Counter(t for _, _, t in al_rows if t)
            potential_saved = set(t_counts_pl) & set(t_counts_al)

            # seen is set of (artist, title) present in al_rows for titles in potential_saved
            seen = {(a, t) for _, a, t in al_rows if t in potential_saved}

            unique_list = []
            similar_list = []
            already_saved = []
            for row in pl_rows:
                i = row.get('id')
                a = row.get('artist')
                tname = row.get('name')
                if tname in potential_saved and (a, tname) in seen:
                    similar_list.append(row)
                    already_saved.append(i)
                else:
                    unique_list.append(row)
                    seen.add((a, tname))

            playlists_out.append({
                'id': p['id'],
                'name': p.get('name'),
                'tracks_count': p.get('tracks', 0),
                'images': p.get('images', []),
                'all_tracks': pl_rows,
                'unique_tracks': unique_list,
                'similar_tracks': similar_list,
            })
            total_matches += len(unique_list) + len(similar_list)

        profile = client.get_user_profile(uid)

        gid = str(uuid4())
        GENERATED[gid] = {
            'id': gid,
            'user': uid,
            'count': total_matches,
            'playlists': playlists_out,
            'profile': profile,
        }

        view_url = url_for('compare_view', gid=gid)
        return jsonify({'ok': True, 'url': view_url, 'count': total_matches})
    except Exception as e:
        app.logger.exception('compare_fetch failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/unique/<gid>')
@login_required
def unique_view(gid):
    g = GENERATED.get(gid)
    if not g:
        flash('Generated playlist not found or expired.', 'error')
        return redirect(url_for('playlists'))
    return render_template('generated_playlist.html', result=g)


@app.route('/similar/<gid>')
@login_required
def similar_view(gid):
    g = GENERATED.get(gid)
    if not g:
        flash('Generated playlist not found or expired.', 'error')
        return redirect(url_for('playlists'))
    return render_template('generated_playlist.html', result=g)


@app.route('/compare/<gid>')
@login_required
def compare_view(gid):
    g = GENERATED.get(gid)
    if not g:
        flash('Generated playlist not found or expired.', 'error')
        return redirect(url_for('playlists'))
    return render_template('generated_playlist.html', result=g)


@app.route('/save_generated/<gid>/<plid>', methods=['POST'])
@login_required
def save_generated(gid, plid):
    """Create a playlist in the current user's account with the filtered tracks
    for the given generated id and playlist id. Returns JSON when requested
    via AJAX, otherwise redirects back to the generated view.
    """
    g = GENERATED.get(gid)
    if not g:
        if request.is_json or request.headers.get('X-Requested-With'):
            return jsonify({'ok': False, 'error': 'Generated result not found'}), 404
        flash('Generated playlist not found or expired.', 'error')
        return redirect(url_for('playlists'))

    # find playlist entry
    pl = None
    for p in g.get('playlists', []):
        if p.get('id') == plid:
            pl = p
            break
    if not pl:
        if request.is_json or request.headers.get('X-Requested-With'):
            return jsonify({'ok': False, 'error': 'Playlist entry not found'}), 404
        flash('Playlist entry not found.', 'error')
        return redirect(url_for('playlists'))

    # Determine which mode to save: 'unique', 'similar', or 'full'
    mode = (request.form.get('mode') or request.args.get('mode') or '').strip().lower()
    if mode == 'unique':
        track_list = pl.get('unique_tracks', [])
    elif mode == 'similar':
        track_list = pl.get('similar_tracks', [])
    else:
        track_list = pl.get('all_tracks', [])

    track_uris = [t.get('uri') for t in track_list if t.get('uri')]
    if not track_uris:
        if request.is_json or request.headers.get('X-Requested-With'):
            return jsonify({'ok': False, 'error': 'No tracks to save'}), 400
        flash('No tracks to save for this playlist.', 'info')
        return redirect(url_for('compare_view', gid=gid))
    # create playlist
    pretty = (mode.title() if mode in ('unique','similar') else 'Playlist')
    name = f"{pretty} - {pl.get('name') or 'Playlist'}"
    created = client.create_playlist_from_tracks(name, track_uris, public=False)
    if not created:
        if request.is_json or request.headers.get('X-Requested-With'):
            return jsonify({'ok': False, 'error': 'Failed to create playlist'}), 500
        flash('Failed to create playlist.', 'error')
        return redirect(url_for('unique_view' if g.get('mode')=='unique' else 'similar_view', gid=gid))

    external = created.get('external_urls', {}).get('spotify') or created.get('uri') or None
    if request.is_json or request.headers.get('X-Requested-With'):
        return jsonify({'ok': True, 'url': external, 'name': created.get('name')})
    flash(f'Created playlist: {created.get("name")}', 'success')
    return redirect(external or url_for('playlists'))


@app.route('/save_tracks', methods=['POST'])
@login_required
def save_tracks():
    # Save selected tracks (from compare panel) to current user's library
    ids = request.form.getlist('track_id')
    compare_user = request.form.get('compare_user') or ''
    if not ids:
        flash('No tracks selected to save.', 'info')
        return redirect(url_for('playlists', compare_user=compare_user) if compare_user else url_for('playlists'))
    ok = client.save_tracks_to_library(ids)
    if ok:
        flash(f'Saved {len(ids)} tracks to your library.', 'success')
    else:
        flash('Failed to save tracks to your library.', 'error')
    return redirect(url_for('playlists', compare_user=compare_user) if compare_user else url_for('playlists'))


@app.route('/merge', methods=['POST'])
@login_required
def merge():
    ids = request.form.getlist('playlist')
    name = request.form.get('name') or 'Merged Playlist'
    if not ids:
        flash('Select at least one playlist.', 'error')
        return redirect(url_for('playlists'))
    playlist = client.merge_playlists(ids, name)
    flash(f"Created merged playlist: {playlist['name']}", 'success')
    return redirect(url_for('playlists'))


@app.route('/clean', methods=['POST'])
@login_required
def clean():
    pid = request.form.get('clean_playlist')
    typed_name = request.form.get('clean_playlist_name')
    name = request.form.get('clean_name')
    if not pid and typed_name:
        pls = client.get_playlists()
        match = None
        for p in pls:
            if p.get('name') and p['name'].strip().lower() == typed_name.strip().lower():
                match = p['id']
                break
        if not match:
            candidates = [p for p in pls if typed_name.strip().lower() in p.get('name','').strip().lower()]
            if not candidates:
                flash('Playlist name not found. Try selecting from the list.', 'error')
                return redirect(url_for('playlists'))
            starts = [p for p in candidates if p.get('name','').strip().lower().startswith(typed_name.strip().lower())]
            chosen = (starts[0] if starts else candidates[0])
            pid = chosen['id']
            if len(candidates) > 1:
                flash(f"Multiple playlists matched the name; using '{chosen['name']}'.", 'info')
    if not pid:
        flash('Select a playlist to clean.', 'error')
        return redirect(url_for('playlists'))
    # Prefer a deterministic cleaned name so we don't overwrite the original.
    original = None
    try:
        plobj = client.get_playlist(pid)
        if plobj and plobj.get('name'):
            original = plobj.get('name')
    except Exception:
        original = None
    if original:
        cleaned_name = f"Cleaned: {original}"
    else:
        cleaned_name = name or None

    # Check whether a playlist with the cleaned name already exists for the
    # current user. If it does and the user has not confirmed overwrite,
    # render a confirmation page before performing the potentially heavy
    # cleaning operation (which scans all playlists).
    existing_pid = None
    existing_empty = False
    try:
        pls = client.get_playlists() or []
        for p in pls:
            if p.get('name') and cleaned_name and p['name'].strip().lower() == cleaned_name.strip().lower():
                tracks_count = p.get('tracks') or 0
                # If the matching playlist has at least one track, we should
                # ask for confirmation before overwriting. If it has zero
                # tracks, we'll treat it as an empty placeholder and overwrite
                # it by default (do not create a second playlist with same name).
                if tracks_count and int(tracks_count) > 0:
                    existing_pid = p['id']
                else:
                    existing_pid = p['id']
                    existing_empty = True
                    app.logger.info("Found existing cleaned playlist '%s' (0 tracks) — will overwrite it by default", cleaned_name)
                break
    except Exception:
        existing_pid = None

    # Respect an explicit overwrite request from the client if provided.
    incoming_overwrite = (request.form.get('overwrite') or request.args.get('overwrite') or '').strip()
    # If the existing playlist was empty and the client didn't explicitly set overwrite,
    # default to overwrite behavior so we don't create duplicate-named playlists.
    overwrite_flag = incoming_overwrite or ('1' if existing_empty else '')

    if existing_pid and overwrite_flag != '1':
        # Ask the user to confirm overwrite before starting heavy processing.
        return render_template('confirm_clean.html', original=original, cleaned_name=cleaned_name, pid=pid)

    # If overwrite_flag == '1' and existing_pid is set, pass that id to
    # the cleaner so it replaces items in-place. Otherwise create a new playlist.
    # If this is an AJAX call, start the clean in a background thread and
    # return a task id so the client can poll progress. For non-AJAX calls
    # continue running synchronously as before.
    is_ajax = (request.is_json or request.headers.get('X-Requested-With'))
    app.logger.info("Starting clean for playlist_id=%s cleaned_name=%s existing_pid=%s overwrite_flag=%s ajax=%s", pid, cleaned_name, existing_pid, overwrite_flag, bool(is_ajax))

    if is_ajax:
        # Capture the user's token info from the session while in request context
        token_info = None
        try:
            token_info = session.get('token_info')
        except Exception:
            token_info = None

        if not token_info or not token_info.get('access_token'):
            return jsonify({'ok': False, 'error': 'No auth token available for background task'}), 403

        access_token = token_info.get('access_token')

        task_id = str(uuid4())
        PROGRESS[task_id] = {'status': 'queued', 'total': 0, 'processed': 0, 'message': 'Queued', 'name': cleaned_name, 'removed': None}

        def run_clean_task(tid, playlist_id, cleaned_name, existing_pid, overwrite_flag, access_token):
            PROGRESS[tid]['status'] = 'running'
            PROGRESS[tid]['message'] = 'Initializing'
            try:
                # create a local SpotifyClient that uses the captured access token
                local_client = SpotifyClient()
                try:
                    local_client.sp = spotipy.Spotify(auth=access_token)
                    # override _ensure_token to avoid touching Flask session from worker thread
                    local_client._ensure_token = lambda: local_client.sp
                except Exception:
                    app.logger.exception('Failed to create spotipy client for background task')
                    PROGRESS[tid].update({'status': 'error', 'message': 'Failed to initialize spotify client'})
                    return

                # Determine total tracks for progress reporting
                try:
                    PROGRESS[tid]['message'] = 'Scanning playlist'
                    tracks_meta = local_client._get_playlist_tracks(playlist_id) or []
                    PROGRESS[tid]['total'] = len(tracks_meta)
                except Exception as ex:
                    app.logger.exception('Failed to list playlist tracks for progress')
                    PROGRESS[tid].update({'status': 'error', 'message': 'Failed to list playlist tracks: ' + str(ex)})
                    return

                def progress_cb(processed, total):
                    PROGRESS[tid]['processed'] = processed
                    PROGRESS[tid]['total'] = total or PROGRESS[tid].get('total', 0)

                PROGRESS[tid]['message'] = 'Processing tracks'
                res = local_client.clean_out_playlist(playlist_id, cleaned_name if not existing_pid else None,
                                                      overwrite_playlist_id=(existing_pid if overwrite_flag == '1' else None),
                                                      progress_cb=progress_cb)
                if not res:
                    PROGRESS[tid].update({'status': 'error', 'message': 'Failed to create or update cleaned playlist'})
                    return
                created, removed = res
                PROGRESS[tid].update({'status': 'done', 'processed': PROGRESS[tid].get('total', 0), 'removed': removed, 'name': created.get('name') if created else cleaned_name, 'message': f'Finished — removed {removed} tracks' if removed is not None else 'Finished'})
            except Exception as e:
                app.logger.exception('clean task failed')
                PROGRESS[tid].update({'status': 'error', 'message': str(e)})

        thread = threading.Thread(target=run_clean_task, args=(task_id, pid, cleaned_name, existing_pid, overwrite_flag, access_token), daemon=True)
        thread.start()
        return jsonify({'ok': True, 'task_id': task_id})

    # Non-AJAX synchronous path: perform cleaning inline (unchanged behavior)
    result = client.clean_out_playlist(pid, cleaned_name if not existing_pid else None,
                                         overwrite_playlist_id=(existing_pid if overwrite_flag == '1' else None))
    if not result:
        flash('Failed to create or update cleaned playlist.', 'error')
        return redirect(url_for('playlists'))
    # client.clean_out_playlist now returns (playlist_obj, removed_count)
    try:
        created_playlist, removed = result
    except Exception:
        created_playlist = result
        removed = None

    playlist_name = created_playlist.get('name') if created_playlist else 'Playlist'
    # Determine whether we created a new playlist or updated an existing one
    is_overwrite = bool(existing_pid and overwrite_flag == '1')

        # Build a human-friendly message we can either flash (normal request)
        # or return as JSON (AJAX request).
    if is_overwrite:
        if removed is None:
            msg = f"Updated '{playlist_name}'"
        else:
            if removed > 0:
                msg = f"Updated '{playlist_name}' — removed {removed} songs from '{original or 'the unclean playlist'}'"
            else:
                msg = f"Updated '{playlist_name}' — no songs were removed from '{original or 'the unclean playlist'}'"
    else:
        if removed is None:
            msg = f"Created playlist: {playlist_name}"
        else:
            if removed > 0:
                msg = f"Created playlist: {playlist_name} — removed {removed} songs from '{original or 'the unclean playlist'}'"
            else:
                msg = f"Created playlist: {playlist_name} — no songs were removed from '{original or 'the unclean playlist'}'"

    # If this was an AJAX request (X-Requested-With header), return JSON
    # with structured information so the client can display a precise toast.
    is_ajax = (request.is_json or request.headers.get('X-Requested-With'))
    if is_ajax:
        return jsonify({'ok': True, 'message': msg, 'name': playlist_name, 'removed': removed, 'updated': is_overwrite})

    # Otherwise use normal flash + redirect flow for full-page navigation.
    flash(msg, 'success')
    return redirect(url_for('playlists'))


@app.route('/update_liked', methods=['POST'])
@login_required
def update_liked():
    spotify = SpotifyClient()
    pname = request.form.get('liked_name') or 'Liked songs as playlist'
    try:
        pl = spotify.update_liked_playlist(pname)
        if pl:
            flash(f"Updated playlist: {pl.get('name')}", 'success')
        else:
            flash('Failed to update liked playlist (no token)', 'error')
    except Exception as e:
        flash(f"Error updating liked playlist: {e}", 'error')
    return redirect(url_for('playlists'))


@app.route('/save_queue', methods=['POST'])
@login_required
def save_queue():
    name = request.form.get('queue_name')
    try:
        playlist, reason = client.save_queue(None, name)
    except Exception as e:
        msg = str(e)
        if 'Permissions missing' in msg or '401' in msg:
            flash("Spotify returned 'Permissions missing'. Reauthorize the app with the full scopes and try again.", 'error')
        else:
            flash(f"Error saving queue: {msg}", 'error')
        return redirect(url_for('playlists'))
    if playlist is None:
        if reason == 'empty':
            flash('Your queue is empty.', 'info')
        elif reason == 'no_playback':
            flash('No active playback detected. Start playback and try again.', 'error')
        elif reason == 'no_current_track':
            flash('Could not determine current track. Start playback and try again.', 'error')
        elif reason == 'no_token':
            flash('Not authorized. Please log in.', 'error')
        else:
            flash('Unable to read/save queue. Make sure you have active playback and try again.', 'error')
        return redirect(url_for('playlists'))
    flash(f"Saved queue to playlist: {playlist['name']}", 'success')
    return redirect(url_for('playlists'))


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    try:
        session.pop('token_info', None)
        session.pop('token', None)
    except Exception:
        app.logger.info('No token info in session to clear')
    return redirect(url_for('index'))


@app.route('/clean_progress/<task_id>')
@login_required
def clean_progress(task_id):
    """Return JSON status for a background clean task id."""
    data = PROGRESS.get(task_id)
    if not data:
        return jsonify({'ok': False, 'error': 'Task not found'}), 404
    return jsonify({'ok': True, 'task_id': task_id, 'status': data.get('status'), 'processed': data.get('processed', 0), 'total': data.get('total', 0), 'message': data.get('message'), 'removed': data.get('removed'), 'name': data.get('name')}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9090, debug=True)
