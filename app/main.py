import os
import logging
import sys
from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory
from werkzeug.exceptions import HTTPException
from app.spotify_client import SpotifyClient

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret-key')

# --- Diagnostics / logging setup -------------------------------------------------
# Configure logger to write to stdout so Vercel captures it in deployment logs.
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
handler.setFormatter(formatter)
if not app.logger.handlers:
    app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)


def _mask_val(v: str) -> str:
    if not v:
        return '<MISSING>'
    return f'<{len(v)} chars>'


def run_startup_diagnostics():
    """Log presence (but not values) of important environment variables.

    Set MANDATORY_ENV_CHECK=1 in the environment (Vercel) to make this
    raise a RuntimeError on missing variables so the deployment fails loudly
    and the stack trace is visible in logs.
    """
    required = [
        'FLASK_SECRET',
        'SPOTIPY_CLIENT_ID',
        'SPOTIPY_CLIENT_SECRET',
        'SPOTIPY_REDIRECT_URI',
    ]
    missing = []
    app.logger.info('Running startup diagnostics...')
    for k in required:
        v = os.getenv(k)
        present = bool(v)
        app.logger.info(f'ENV {k}: present={present} ({_mask_val(v)})')
        if not present:
            missing.append(k)

    # Log if session currently has token_info (useful for debugging auth flows)
    try:
        has_token = 'token_info' in session
        app.logger.info(f'session has token_info: {has_token}')
    except Exception:
        # session may not be available at import-time in some WSGI setups; swallow silently
        app.logger.info('session object not available at startup')

    if missing:
        app.logger.warning(f'Missing required env vars: {missing}')
        if os.getenv('MANDATORY_ENV_CHECK') == '1':
            raise RuntimeError(f'Missing required env vars: {missing}')


# Run diagnostics now (non-fatal by default)
try:
    run_startup_diagnostics()
except Exception:
    app.logger.exception('Startup diagnostics failed')
    raise

# Instantiate Spotify client after diagnostics so any exceptions are logged cleanly
client = SpotifyClient()


# Global error handler to log full tracebacks to Vercel logs
@app.errorhandler(Exception)
def handle_unexpected_error(error):
    # For HTTP exceptions (404, 400, etc.) return their proper status code
    # without treating them as internal server errors. This prevents requests
    # like `/favicon.ico` from showing up as a 500 in logs when the client
    # simply requested a missing static file.
    if isinstance(error, HTTPException):
        app.logger.info(f'HTTP exception during request: {error}')
        return error.description, error.code

    app.logger.exception('Unhandled exception during request')
    # Return a generic 500 to the client; the logs will contain details
    return 'Internal Server Error', 500

# Log incoming requests (path + method) to help trace 500s
@app.before_request
def log_request_info():
    app.logger.info(f'Incoming request: {request.method} {request.path}')
    try:
        app.logger.info(f'session keys: {list(session.keys())}')
    except Exception:
        pass


@app.route('/favicon.ico')
def favicon():
    """Attempt to serve a favicon from the static folder; if missing, return
    204 No Content so clients don't trigger a 404->500 in our logs.
    """
    try:
        return send_from_directory(app.static_folder, 'favicon.ico')
    except Exception:
        # Don't raise — browsers will survive without a favicon.
        return ('', 204)


@app.route("/")
def index():
    # If Spotify redirected here with an authorization code (some apps register redirect URI without /callback)
    code = request.args.get('code')
    error = request.args.get('error')
    if error:
        flash(f"Spotify authorization error: {error}", "error")
        return render_template("index.html")
    if code:
        sp = client.handle_callback(request.args)
        if not sp:
            flash("Authorization failed.", "error")
            return render_template("index.html")
        return redirect(url_for('playlists'))

    user = client.get_current_user()
    if user:
        return redirect(url_for('playlists'))
    return render_template("index.html")


@app.route("/login")
def login():
    url = client.get_authorize_url()
    return redirect(url)


@app.route("/callback")
def callback():
    sp = client.handle_callback(request.args)
    if not sp:
        flash("Authorization failed.", "error")
        return redirect(url_for('index'))
    return redirect(url_for('playlists'))


@app.route("/playlists")
def playlists():
    pls = client.get_playlists()
    user = client.get_current_user()
    return render_template("playlists.html", playlists=pls, user=user)


@app.route("/merge", methods=["POST"])
def merge():
    ids = request.form.getlist("playlist")
    name = request.form.get("name") or "Merged Playlist"
    if not ids:
        flash("Select at least one playlist.", "error")
        return redirect(url_for('playlists'))
    playlist = client.merge_playlists(ids, name)
    flash(f"Created merged playlist: {playlist['name']}", "success")
    return redirect(url_for('playlists'))


@app.route("/clean", methods=["POST"])
def clean():
    pid = request.form.get("clean_playlist")
    typed_name = request.form.get("clean_playlist_name")
    name = request.form.get("clean_name")

    # If user typed a playlist name, try to resolve to an ID (case-insensitive exact match) - smarter matching using difflib
    if not pid and typed_name:
        pls = client.get_playlists()
        match = None
        for p in pls:
            if p.get('name') and p['name'].strip().lower() == typed_name.strip().lower():
                match = p['id']
                break
            if not match:
                # try fuzzy matching (startswith / contains)
                candidates = [p for p in pls if typed_name.strip().lower() in p.get('name','').strip().lower()]
                if not candidates:
                    flash("Playlist name not found. Try selecting from the list or check the exact name.", "error")
                    return redirect(url_for('playlists'))
                # if multiple candidates, pick the best (startswith) or first; notify user
                starts = [p for p in candidates if p.get('name','').strip().lower().startswith(typed_name.strip().lower())]
                chosen = (starts[0] if starts else candidates[0])
                pid = chosen['id']
                if len(candidates) > 1:
                    flash(f"Multiple playlists matched the name; using '{chosen['name']}'. Consider selecting from the list if this is wrong.", "info")

    if not pid:
        flash("Select a playlist to clean or enter its exact name.", "error")
        return redirect(url_for('playlists'))

    playlist = client.clean_out_playlist(pid, name)
    flash(f"Created cleaned playlist: {playlist['name']}", "success")
    return redirect(url_for('playlists'))


@app.route('/update_liked', methods=['POST'])
def update_liked():
    spotify = SpotifyClient()
    pname = request.form.get('liked_name') or 'Liked songs as playlist'
    try:
        pl = spotify.update_liked_playlist(pname)
        if pl:
            flash(f"Updated playlist: {pl.get('name')}")
        else:
            flash("Failed to update liked playlist (no token)")
    except Exception as e:
        flash(f"Error updating liked playlist: {e}")
    return redirect(url_for('playlists'))


@app.route("/save_queue", methods=["POST"])
def save_queue():
    # Automated flow: no pasted input required. Provide optional name.
    name = request.form.get("queue_name")
    try:
        playlist, reason = client.save_queue(None, name)
    except Exception as e:
        # If SpotifyException with 401 permissions missing, give actionable message
        msg = str(e)
        if 'Permissions missing' in msg or '401' in msg:
            flash("Spotify returned 'Permissions missing'. Reauthorize the app with the full scopes and try again.", "error")
        else:
            flash(f"Error saving queue: {msg}", "error")
        return redirect(url_for('playlists'))
    # Handle specific failure reasons to give clearer feedback
    if playlist is None:
        if reason == 'empty':
            flash("Your queue appears to be empty.", "info")
        elif reason == 'no_playback':
            flash("No active playback detected. Start playback in Spotify and try again.", "error")
        elif reason == 'no_current_track':
            flash("Could not determine current track. Start playback and try again.", "error")
        elif reason == 'no_token':
            flash("Not authorized. Please log in.", "error")
        else:
            flash("Unable to read/save queue. Make sure you have active playback and try again.", "error")
        return redirect(url_for('playlists'))
    flash(f"Saved queue to playlist: {playlist['name']}", "success")
    return redirect(url_for('playlists'))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090, debug=True)
