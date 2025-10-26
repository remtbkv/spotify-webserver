from app.spotify_client import SpotifyClient

def merge_playlists(playlist_ids, user_id):
    combined_tracks = set()
    new_playlist_name = "Merged Playlist"
    
    for playlist_id in playlist_ids:
        tracks = SpotifyClient.get_playlist_tracks(playlist_id)
        for track in tracks:
            combined_tracks.add(track['id'])
    
    new_playlist_id = SpotifyClient.create_playlist(user_id, new_playlist_name)
    SpotifyClient.add_tracks_to_playlist(new_playlist_id, list(combined_tracks))

    return new_playlist_id

def clean_out_playlist(playlist_id, saved_tracks):
    current_tracks = SpotifyClient.get_playlist_tracks(playlist_id)
    tracks_to_keep = [track for track in current_tracks if track['id'] not in saved_tracks]
    
    new_playlist_name = "Cleaned Playlist"
    new_playlist_id = SpotifyClient.create_playlist(SpotifyClient.get_user_id(), new_playlist_name)
    SpotifyClient.add_tracks_to_playlist(new_playlist_id, [track['id'] for track in tracks_to_keep])

    return new_playlist_id

def save_queue(queue_tracks, user_id):
    new_playlist_name = "Saved Queue"
    new_playlist_id = SpotifyClient.create_playlist(user_id, new_playlist_name)
    SpotifyClient.add_tracks_to_playlist(new_playlist_id, [track['id'] for track in queue_tracks])

    return new_playlist_id