from app.spotify_client import SpotifyClient

def save_queue_to_playlist(user_id, playlist_name, queue_tracks):
    spotify_client = SpotifyClient()
    
    # Create a new playlist for the user
    playlist_id = spotify_client.create_playlist(user_id, playlist_name)
    
    # Add tracks from the queue to the new playlist
    track_ids = [track['id'] for track in queue_tracks]
    spotify_client.add_tracks_to_playlist(playlist_id, track_ids)
    
    return playlist_id

def get_user_queue(user_id):
    spotify_client = SpotifyClient()
    return spotify_client.get_user_queue(user_id)