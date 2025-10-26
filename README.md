<<<<<<< HEAD
# spotify-webserver
=======
# Spotify Manager

## Overview
Spotify Manager is a web application that allows users to manage their Spotify playlists efficiently. It provides functionalities to merge playlists, clean out duplicates, and save the user's queue to a playlist.

## Features
- **Merge Playlists**: Create a new merged playlist without duplicates.
- **Clean Out Playlist**: Generate a new playlist with already-saved tracks removed.
- **Save Queue**: Save the user's added queue to a playlist.

## Getting Started

### Prerequisites
- Python 3.x
- pip (Python package installer)

### Installation
1. Clone the repository:
   ```
   git clone <repository-url>
   cd spotify-manager
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a Spotify app by following the instructions [here](https://developer.spotify.com/documentation/web-api/concepts/apps). 

4. Create a `.env` file in the root directory with the following content:
   ```
   SPOTIPY_CLIENT_ID = <your_client_id>
   SPOTIPY_CLIENT_SECRET = <your_client_secret>
   SPOTIPY_REDIRECT_URI = http://127.0.0.1:9090
   ```

### Running the Application
To start the application, run:
```
python app/main.py
```

### OAuth Flow
The application implements the OAuth flow for user authentication with the Spotify API. When you run the application, it will prompt you to authenticate and authorize access to your Spotify account.

### Web App
A web app version is in development, which will simplify the process to a single button click for managing playlists.

## Contributing
Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for details.
>>>>>>> 364c348 (Initial commit - import project)
