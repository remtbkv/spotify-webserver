from flask import Blueprint, redirect, request, session, url_for
import os, spotipy
from spotipy.oauth2 import SpotifyOAuth

auth_bp = Blueprint('auth', __name__)

# Configure Spotify OAuth
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI')

sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                        client_secret=SPOTIPY_CLIENT_SECRET,
                        redirect_uri=SPOTIPY_REDIRECT_URI,
                        scope='playlist-modify-public playlist-modify-private user-read-private user-read-email')

@auth_bp.route('/login')
def login():
    return redirect(sp_oauth.get_authorize_url())

@auth_bp.route('/callback')
def callback():
    token_info = sp_oauth.get_access_token(request.args['code'])
    session['token_info'] = token_info
    return redirect(url_for('main.index'))


def get_token():
    token_info = session.get('token_info', {})
    if not token_info:
        return None
    return token_info['access_token'] if not sp_oauth.is_token_expired(token_info) else None

def get_spotify_client():
    token = get_token()
    if token:
        return spotipy.Spotify(auth=token)
    return None