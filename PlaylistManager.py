from collections import Counter
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
from datetime import datetime
import spotipy, pickle, re, time
load_dotenv()


"""
# TODO:

Use recommendations(seed_artists=None, seed_genres=None, seed_tracks=None, limit=20, country=None, **kwargs)
recursively to create playlist with n number of recs that aren't already saved (or have been listened to?)

Host website to keep track of all listened songs, lowk a discord bot would also be easy (free)

Allow user to visually mergesort songs in a playlist by how much they like it

I had an error near 95 songs in queue, need replicate and fix

Cant mute when on phone: HTTP Error for PUT to https://api.spotify.com/v1/me/player/volume?volume_percent=0 with Params: {} returned 403 due to Player command failed: Cannot control device volume

"""


class Cleaner:
    """
    Main functions:
    - merge_playlists : creates new merged playlist without duplicates
    - clean_out_playlist : creates new playlist with already-saved tracks removed
    - save_queue : saves user's added queue to a playlist

    Utility functions:
    - find_listened_songs_from_playlist : check last 24 hours of listening history for a specific playlist
    - check_playlist_for_duplicates : displays duplicate titles, if any
    - remove_songs_from_playlist : creates new playlist with songs removed
    - print_playlists : lists playlist ids and names
    - print_info : displays track information in alphabetical order by title
    - backup_playlist : writes songs to .txt
    - dump_tracks : dumps all tracks to a pickle file
    - load_tracks : loads tracks from a pickle file
    """

    def __init__(self, debug=False):
        """
        Initialize spotify client with necessary scopes
        """
        scopes = "\
            user-library-read \
            playlist-read-private \
            playlist-read-collaborative \
            playlist-modify-private \
            playlist-modify-public \
            user-read-playback-state \
            user-read-recently-played \
            user-read-currently-playing \
            user-read-playback-position \
            user-modify-playback-state \
            "
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scopes))
        self.user_id = self.sp.current_user()['id']
        if not debug:
            self.driver()

    def driver(self):
        block = "="*32
        functs = [  "clean out playlist",
                    "merge playlists",
                    "save queue",
                    "update liked playlist",
                    "manage 'others' playlist"]
        s = "\n".join(f"  [{i}]: {f}" for i, f in enumerate(functs, 1))
        prompt = f"{block}\n What do you wish for, my king?\n\n{s}\n\n Press any other key to exit\n{block}\n\n"
        choice = input(prompt)
        if not len(choice) or not choice[0].isdigit():
            return
        match int(choice[0]):
            case 1:
                playlist = input("Which playlist? Enter ID or name: ")
                if new_pn := self.clean_out_playlist(playlist):
                    print(f"Created clean playlist: '{new_pn[0]}'")
                    if len(new_pn) == 2:
                        print(f"Backed up songs to: '{new_pn[1]}'")
            case 2:
                inp = input("Enter playlist IDs or names separated by a semicolon.\n\Example: Bob Marley;12FZ76na1B12z8ELM;favorite playlist\nEnter: ")
                sources = inp.split(";")
                if new_pn := self.merge_sources(sources):
                    print(f"Created merged playlist: '{new_pn}'")
            case 3:
                if new_pn := self.save_queue():
                    print(f"Saved queue to: '{new_pn}'")
            case 4:
                if diff := self.liked_songs_as_playlist():
                    print(f"Updated playlist with {'+' if diff > 0 else ''}{diff} change{('s' if abs(diff)>1 else '')}")
            case 5:
                if smaller := self.manage_others():
                    print(f"Updated '{smaller}' playlist")
            case _:
                return
        cont = input("Anything else? (y = yes, enter = no) ")
        if len(cont):
            print()
            self.driver()

    def merge_playlists(self, sources):
        """
        Creates new merged playlist without crossovers. 
        Playlists are appended in order

        Parameters:
            sources: list of playlist ids or names
                - if name is provided of which multiple playlists exist, this merges all

        Returns playlist name
        """
        sources = self.validate_sources(sources)
        pnames = [self.sp.playlist(id)['name'] for id in sources]
        pname = " + ".join(pnames)
        if not (new_pl := self.create_pl(pname)):
            print("Aborted")
            return

        songs = self.get_tracks(sources)
        title_counts = Counter(t for *_, t in songs)
        uniques, seen = [], set()
        for i, a, t in songs:
            key = (a, t)
            if title_counts[t] == 1 or key not in seen:
                uniques.append(i)
                seen.add(key)

        self.add_tracks(new_pl, uniques)
        return pname

    def clean_out_playlist(self, playlist, to_return=[]):
        """
        Creates new playlist with already-saved tracks removed.
        Can backup removed songs
        
        Parameters:
            playlist: name or id
        
        Returns name of new playlist, or list if there are 2 (another backed up)
        """
        pid = self.validate_sources([playlist])[0]
        name = self.sp.playlist(pid)['name']
        pname1 = "Cleaned: " + name
        if not (new_pl := self.create_pl(pname1)):
            print("Aborted")
            return
        to_return.append(pname1)
        pl_tracks, al_tracks = self.get_tracks(pid), self.get_tracks(everything=True, excepted=pid)
        t_counts_pl, t_counts_al = Counter(t for *_, t in pl_tracks), Counter(t for *_, t in al_tracks)
        potential_saved = set(t_counts_pl) & set(t_counts_al)
        uniques, seen, already_saved = [], set(), []
        seen = {(a, t) for _, a, t in al_tracks if t in potential_saved}
        for i, a, t in pl_tracks:
            if t in potential_saved and (a, t) in seen:
                already_saved.append(i)
            else:
                uniques.append(i)
                seen.add((a, t))

        self.add_tracks(new_pl, uniques)
        if (n_rem := len(already_saved)) == 0:
            print("No duplicates or songs already saved")
            return
        choice = input(f"Would you like to backup the {n_rem} removed songs? (y/n): ").lower()
        if choice == 'y':
            pname2 = "Dupes removed from: " + name
            if not (new_pl := self.create_pl(pname2)):
                print("Aborted")
                return
            self.add_tracks(new_pl, already_saved)
            to_return.append(pname2)
        return to_return[0] if len(to_return)==1 else to_return
    
    def save_queue(self):
        """
        Saves current queue to playlist. Spotify only allows up to 100 queued songs

        Returns name of playlist
        """
        SPOTIFY_QUEUE_LIMIT = 100
        DUMMY = "6sVK7RXMHRGxAefiqEGEbP" # "bittersweet" by $up1, surely not to be in anyone's queue
        pname = "Saved queue"
        muted = True

        cp = self.sp.current_playback()
        if not cp:
            print("No active playback")
            return
        position = cp['progress_ms']
        if not cp['is_playing']:
            self.sp.start_playback()
        try:
            volume = cp['device']['volume_percent']
            self.sp.volume(0)
            print("Volume muted")
        except:
            muted = False
            print("Error muting volume, probably because you're on phone")
        self.sp.add_to_queue(DUMMY)
        self.sp.add_to_queue(cp['item']['id'])
        self.sp.next_track()
        time.sleep(0.25)
        n, q, curr =  0, [], self.get_curr()
        while curr != DUMMY:
            if n==SPOTIFY_QUEUE_LIMIT-7:
                print("Sleeping for 10 seconds to allow for queue in API to update")
                time.sleep(10)
            q.append(curr)
            self.sp.next_track()
            time.sleep(0.25)
            next_id = curr
            start = time.time()
            while next_id == curr:
                next_id = self.get_curr()
                time.sleep(0.1)
                if time.time() - start > 1.25:
                    start = time.time()
                    print("waited 1.25 s")
                    self.sp.next_track()
                    next_id = self.get_curr()
            curr = next_id
        self.sp.next_track()
        time.sleep(0.25)
        self.sp.seek_track(position)

        if muted:
            self.sp.volume(volume)
        print("Volume restored")
        if not q:
            print("No queue")
            return
        new_pl = self.sp.user_playlist_create(self.user_id, pname, public=False)['id']
        self.add_tracks(new_pl, q)
        return pname
            
    def backup_playlist(self, pid, fn):
        """
        Writes songs from playlist to a text file.
        
        Parameters:
            pid: playlist id
            fn: filename without extension
        """
        ids, *_ = zip(*self.get_tracks(pid))
        with open(fn+".txt", "w+") as f:
            for id in ids:
                f.write(id+'\n')
        print("Saved")

    def find_listened_songs_from_playlist(self, playlist):
        """
        Returns a list of song IDs listened to from a playlist.
        Only fetches last 24 hours

        Parameters:
            playlist: playlist id or name
        """
        listened_songs = []
        prev_unix = int(datetime.now().timestamp())*1000
        pid = self.validate_sources([playlist])[0]
        while True:
            recently_played = self.sp.current_user_recently_played(before=prev_unix)
            if not recently_played['items']:
                break
            for item in recently_played['items']:
                track = item['track']
                dt = datetime.strptime(item['played_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
                prev_unix = int(dt.timestamp()*1000 - 1e8) 
                try:
                    if item['context']['uri'].endswith(pid):
                        id, artist, title = track['id'], track['artists'][0]['name'], track['name']
                        listened_songs.append((id, artist, title))
                except:
                    continue
        # for i,a,t in listened_songs:
        #     print(f"Listened to {t} by {a} ({i})")
        return [i[0] for i in listened_songs]

    def check_playlist_for_duplicates(self, playlist):
        pid = self.validate_sources([playlist])[0]
        pl_tracks = self.get_tracks(pid)
        dupes, seen, t_counts = [], set(), Counter(t for _, _, t in pl_tracks)
        for i, a, t in pl_tracks:
            if t_counts[t] > 1:
                if (a, t) not in seen:
                    seen.add((a, t))
                else:
                    dupes.append((i,a,t))
        if dupes:
            for i, a, t in dupes:
                print(f"{t} by {a} ({i})")
            return dupes
        else:
            print("No duplicates!")
            return None

    def remove_songs_from_playlist(self, playlist, ids):
        """
        Creates new playlist with the specified songs removed.

        Parameters:
            playlist : playlist id or name
            ids: list of song IDs
        """
        pid = self.validate_sources([playlist])[0]
        pl_tracks = self.get_tracks(pid)
        unique_ids = [i[0] for i in pl_tracks if i[0] not in ids]
        n_removed = len(pl_tracks) - len(unique_ids)
        pname = f"{n_removed} removed: {self.sp.playlist(pid)['name']}"
        if not (new_pl := self.create_pl(pname)):
            print("Aborted")
            return
        self.add_tracks(new_pl, unique_ids)
        print(f"See new playlist at '{pname}'")

    def liked_songs_as_playlist(self):
        """
        Store liked songs as a playlist. Updates to exactly match liked songs.
        """
        pname = "Liked songs as playlist"
        pid = self.create_pl(pname, return_existing=True)
        n = self.sp.playlist(pid)['tracks']['total']
        songs = [i[0] for i in self.get_tracks()]
        self.sp.playlist_replace_items(pid, [])
        self.add_tracks(pid, songs)
        return len(songs)-n

    def manage_others(self, others="others"):
        # songs = self.get_tracks(others)
        songs = self.load_tracks(fn="others")

        moved, a_songs, a_counts = [], {}, Counter(a for _, a, _ in songs)
        for i, a, _ in songs:
            if a in a_songs:
                a_songs[a].append(i)
            else:
                a_songs[a] = [i]
        my_saved_pls = {i[1]: i[0] for i in self.get_my_playlists(only_mine=True)}
        for a, n in a_counts.most_common():
            if n > 7:
                moved += (ids := a_songs[a])
                pname = f"{a} - others"
                if pname in my_saved_pls:
                    pid = my_saved_pls[pname]
                    if {i for i, *_ in self.get_tracks(pid)} == set(ids):
                        print(f"Identical playlist already exists for {a}")
                        continue
                else:
                    pid = self.create_pl(f"{a} - others", check=False)
                self.sp.playlist_replace_items(pid, [])
                self.add_tracks(pid, ids)
                print(f"Created playlist for {a} with {n} songs")
        leftover_ids = [i for i, _, _ in songs if i not in moved]
        pname = "smaller others"
        pid = self.create_pl(pname, return_existing=True)
        self.sp.playlist_replace_items(pid, [])
        self.add_tracks(pid, leftover_ids)
        print(f"Updated '{pname}' playlist")
        return pname

        # see distribution of artists with number of songs
        # counts = {i: [] for i in set(a_counts.values())}
        # for artist, count in a_counts.most_common():
        #     counts[count].append(artist)
        # for i in counts:
            # if i>1:
            #     print(i)
            #     for j in counts[i]:
            #         print(f"  {j}")
            #     print()

    def print_playlists(self, only_mine=True):
        """
        Displays playlist ids and titles.
            - If only_mine is True, only shows playlists created by the user

        Parameters:
            only_mine: boolean
        """
        for id, name in self.get_my_playlists(only_mine=only_mine):
            print(id, name)

    def print_info(self, info):
        """
        Prints track information in alphabetical order by title.

        Parameters:
            info: set of tuples describing tracks
        """
        for id, artist, title in sorted(info, key=lambda x: x[2].lower()):
            print(f"{title} - {artist} ({id})")

    def dump_tracks(self, fn='tracks', tracks=None, **kwargs):
        """
        Dumps tracks to a pickle file.

        Parameters:
            fn: filename without extension
            tracks: list of tuples describing tracks (id, artist, title)
            **kwargs: passed directly to get_tracks (e.g., sources, everything, liked_songs)
        """
        with open(fn+'.pkl', 'wb') as f:
            if tracks:
                pickle.dump(tracks, f)
            else:
                pickle.dump(self.get_tracks(**kwargs), f)
        print("Pickle saved")

    def load_tracks(self, fn):
        """
        Loads tracks from a pickle file.

        Parameters:
            fn: filename without extension
        """
        return pickle.load(open(fn+'.pkl', 'rb'))

    def load_playlist_from_profile(self):
        """
        Loads playlist IDs from a user's public profile.

        Parameters:
            user: spotify user id
        """
        user = "https://open.spotify.com/user/yysrukbk3ie87hkkw2pqyqwj3?si=4d008dc294bc46f0"
        user = user.split("?")[0].split("/")[-1]
        items = self.get_all([self.sp.user_playlists(user)])

        
    # Helper
    def get_all(self, sources):
        """
        Fetches all items from paginated sources.

        Parameters:
            sources: list of paginated sources
        """
        items = []
        for source in sources:
            items += source["items"]
            while source['next']:
                source = self.sp.next(source)
                items += source["items"]
        return items

    # Helper
    def get_tracks(self, sources=None, fn=None, excepted=[], everything=False, liked_songs=False, only_mine=True):
        """
        Returns list of tuples describing track (id, artist, title).
        Excludes episodes, local files, and duplicate IDs.
            - If sources is empty, defaults to liked songs
            - If everything is True, includes liked songs and all playlists created by the user
            - If liked_songs is True, includes liked songs in the sources
            - If fn is provided, loads from a pickle file to optimize loading
            - If liked_songs is True, includes liked songs in the sources

        Parameters:
            sources : list of playlist ids
            fn : filename to load from pickle
            excepted : list of playlist ids to ignore
            everything : boolean
            liked_songs : boolean
        """
        if fn is not None:
            with open(fn+".pkl", "rb") as f:
                return pickle.load(f)
        else:
            sources, excepted = self.validate_sources(sources), self.validate_sources(excepted)
            
            if sources:
                track_pages = [self.sp.playlist(id)['tracks'] for id in [id_keep for id_keep in sources if id_keep not in excepted]]
                if liked_songs:
                    track_pages.append(self.sp.current_user_saved_tracks())
            else:
                track_pages = [self.sp.current_user_saved_tracks()]
                if everything:
                    other_pls = [i[0] for i in self.get_my_playlists(only_mine) if i[0] not in excepted]
                    track_pages += [self.sp.playlist(id)['tracks'] for id in other_pls]
                
            items, info = self.get_all(track_pages), {}
            for track in items:
                if track['track'] and track['track']['id'] and track["track"]['artists'][0]['name']:
                    info[track["track"]["id"]] = (track["track"]['artists'][0]['name'], track["track"]['name'])
            info = [(id, artist, title) for id, (artist, title) in info.items()]
            return info

    # Helper
    def get_pid(self, playlist_name, to_return=[]):
        """
        Returns the playlist id(s) given the name
         - if 1, returns the string id
         - if multiple, returns a list containing the ids
        """
        for id, name in self.get_my_playlists(only_mine=True):
            if playlist_name == name:
                to_return.append(id)
        if to_return:
            if len(to_return) == 1:
                return to_return[0]
            return to_return
        return None
   
   # Helper
    def get_my_playlists(self, only_mine=True):
        """
        Returns alphabetically sorted list of playlists as tuples -> id, title
        
        only_mine = None -> gets all playlists, not just my created ones
        """   
        items, pls = self.get_all([self.sp.current_user_playlists()]), []
        for pl in items:
            if (not only_mine) or (only_mine and pl['owner']['id'] == self.user_id):
                pls.append((pl['id'], pl['name']))
        return sorted(pls, key=lambda x: x[1].lower())

    # Helper
    def create_pl(self, playlist_name, check=True, return_existing=False):
        """
        Returns id of playlist
        """
        if check:
            for id, name in self.get_my_playlists(only_mine=True):
                if name == playlist_name:
                    s = "Playlist already exists with {} songs. Enter 'y' to continue: ".format(self.sp.playlist(id)['tracks']['total'])
                    return id if return_existing or input(s).lower() == 'y' else None
        return self.sp.user_playlist_create(self.user_id, playlist_name, public=False)['id']
    
    # Helper
    def add_tracks(self, pid, ids):
        """
        Adds tracks to playlist in batches of 100 to avoid API limits.

        Parameters:
            pid: playlist id
            ids: list of track ids to add
        """
        for i in range(0, len(ids), 100):
            self.sp.playlist_add_items(pid, ids[i:i+100])
    
    # Helper
    def validate_sources(self, sources):
        """
        Returns a list of valid sources (all IDs).

        Parameters:
            sources: list of playlist ids or names
        """
        def is_id(s):
            has_len = len(s) == 22
            has_digit = bool(re.search(r'\d', s))
            has_upper = bool(re.search(r'[A-Z]', s))
            has_lower = bool(re.search(r'[a-z]', s))
            return has_len and has_digit and has_upper and has_lower
        if sources is None:
            return None
        if type(sources) == str:
            sources = [sources]
        
        id_name = {id: name for id, name in self.get_my_playlists(only_mine=False)}
        ids = []
        for source in sources:
            if is_id(source) and source in id_name:
                ids.append(source)
            elif source in id_name.values():
                for id, name in id_name.items():
                    if name == source:
                        ids.append(id)
        return ids

    # Helper
    def get_curr(self):
        """
        Returns id of current song being played
        """
        return self.sp.currently_playing()['item']['id']

    # Helper
    def sort_by_most_listened(self, songs=None, source="smaller others"):
        """
        Sorts songs by popularity (0-100) on Spotify and writes to most_listened.txt

        Parameters:
            songs: list of tuples describing tracks (id, artist, title)
            source: playlist id or name to fetch songs from if songs is None
        """
        if songs is None:
            songs = self.get_tracks(source)
        most_listened = []
        z=0
        for i, *_ in songs:
            if z%50==0:
                time.sleep(0.2)
                print(f"Processed {z} songs")
            z+=1
            tr = self.sp.track(i)
            n = tr['popularity']
            most_listened.append((i, n))
        most_listened.sort(key=lambda x: x[1], reverse=True)
        with open("most_listened.txt", "w+") as f:
            for i, n in most_listened:
                f.write(f"{i} {n}\n")
        return [i for i, _ in most_listened]


# sp = Cleaner(debug=False)
sp = Cleaner(debug=True)
sp.load_playlist_from_profile()