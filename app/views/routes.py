from flask import Blueprint, request, redirect, session, url_for
from app.auth import get_auth_url, get_token, get_user_playlists
from app.spotify_client import SpotifyClient

routes = Blueprint('routes', __name__)

@routes.route('/')
def index():
    return "Welcome to Spotify Manager!"

@routes.route('/login')
def login():
    auth_url = get_auth_url()
    return redirect(auth_url)

@routes.route('/callback')
def callback():
    token = get_token(request.args.get('code'))
    session['token'] = token
    return redirect(url_for('routes.user_playlists'))

@routes.route('/playlists')
def user_playlists():
    if 'token' not in session:
        return redirect(url_for('routes.login'))
    
    spotify_client = SpotifyClient(session['token'])
    playlists = get_user_playlists(spotify_client)
    return {"playlists": playlists}  # You can render a template here instead

@routes.route('/logout')
def logout():
    session.pop('token', None)
    return redirect(url_for('routes.index'))