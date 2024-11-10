import re
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import tkinter as tk
from tkinter import filedialog, simpledialog
from tqdm import tqdm
import requests
import urllib3
from requests.adapters import HTTPAdapter

# Add your credentials here
CLIENT_ID = "97d992961a9144b6ba56bf49e5a78963"
CLIENT_SECRET = "adc8011c470a4c4ea24892b119ac640c"
REDIRECT_URI = "http://localhost:8888/callback"

def extract_playlist_id(url):
    """Extract playlist ID from Spotify URL."""
    # Handle both playlist URLs and URIs
    patterns = [
        r'spotify:playlist:([a-zA-Z0-9]{22})',           # Spotify URI
        r'open\.spotify\.com/playlist/([a-zA-Z0-9]{22})', # Web URL
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_playlist_url():
    """Open a dialog to get the target playlist URL."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    while True:
        url = simpledialog.askstring(
            "Playlist URL", 
            "Enter the Spotify playlist URL where you want to add the tracks:\n"
            "(e.g., https://open.spotify.com/playlist/...)",
            parent=root
        )
        
        if not url:
            return None
            
        playlist_id = extract_playlist_id(url)
        if playlist_id:
            return playlist_id
        else:
            tk.messagebox.showerror(
                "Invalid URL",
                "Please enter a valid Spotify playlist URL.\n"
                "It should look like: https://open.spotify.com/playlist/..."
            )

def create_spotify_client():
    """Create a Spotify client with custom session settings."""
    session = requests.Session()

    retry = urllib3.Retry(
        total=0,
        connect=None,
        read=0,
        allowed_methods=frozenset(['GET', 'POST', 'PUT', 'DELETE']),
        status=0,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        respect_retry_after_header=False
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    SCOPE = "playlist-modify-public playlist-modify-private playlist-read-private"
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    )
    
    return spotipy.Spotify(
        auth_manager=auth_manager,
        requests_session=session
    )

def select_chat_file():
    """Open a file dialog and return the selected file path."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(
        title="Select WhatsApp Chat Export",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    return file_path

def extract_spotify_tracks_with_context(chat_content):
    """Extract only Spotify track URLs with surrounding text context."""
    pattern = r'([^\n]*?https://open\.spotify\.com/track/([a-zA-Z0-9]{22})[^\n]*)'
    matches = re.finditer(pattern, chat_content)
    return list(matches)

def get_playlist_tracks(sp, playlist_id, desc="Loading playlist tracks"):
    """Get all track IDs from a playlist."""
    tracks = set()
    try:
        results = sp.playlist_tracks(playlist_id)
        total = results['total']
        
        with tqdm(total=total, desc=desc) as pbar:
            while results:
                for item in results['items']:
                    if item['track']:
                        tracks.add(item['track']['id'])
                    pbar.update(1)
                if results['next']:
                    results = sp.next(results)
                else:
                    break
    except Exception as e:
        print(f"Error getting tracks from playlist {playlist_id}: {str(e)}")
    
    return tracks

def add_tracks_to_playlist(sp, playlist_id, tracks):
    """Add tracks to playlist."""
    if tracks:
        try:
            sp.playlist_add_items(playlist_id, tracks)
            print(f"Added {len(tracks)} tracks to playlist")
            return True
        except Exception as e:
            print(f"Error adding tracks to playlist: {str(e)}")
            return False
    return False

def verify_playlist_access(sp, playlist_id):
    """Verify that the user has access to modify the playlist."""
    try:
        # Try to get the playlist
        playlist = sp.playlist(playlist_id)
        
        # Try to get the current user
        current_user = sp.current_user()
        
        # Check if the playlist belongs to the current user
        is_owner = playlist['owner']['id'] == current_user['id']
        
        # If not owner, check if the playlist is collaborative
        if not is_owner and not playlist['collaborative']:
            print("Warning: You don't own this playlist and it's not collaborative.")
            print("You may not have permission to add tracks.")
            return False
            
        return True
        
    except Exception as e:
        print(f"Error verifying playlist access: {str(e)}")
        return False

def process_matches(sp, matches, existing_tracks, target_playlist_id):
    """Process all matches from the chat file and add tracks immediately."""
    total_added = 0
    current_batch = []
    
    with tqdm(total=len(matches), desc="Processing tracks") as pbar:
        for match in matches:
            track_id = match.group(2)  # Direct track ID from URL
            
            if track_id not in existing_tracks:
                current_batch.append(track_id)
                existing_tracks.add(track_id)
                
                # Add batch when it reaches 50 tracks
                if len(current_batch) >= 50:
                    if add_tracks_to_playlist(sp, target_playlist_id, current_batch):
                        total_added += len(current_batch)
                    current_batch = []
            
            pbar.update(1)
    
    # Add any remaining tracks in the final batch
    if current_batch:
        if add_tracks_to_playlist(sp, target_playlist_id, current_batch):
            total_added += len(current_batch)
    
    return total_added

def main():
    try:
        # Set up Spotify client with custom session
        sp = create_spotify_client()
        
        # Test the connection
        sp.current_user()
        
    except Exception as e:
        print("Error setting up Spotify connection:")
        print(f"Make sure you've filled in your CLIENT_ID and CLIENT_SECRET at the top of the script")
        print(f"Error details: {str(e)}")
        return
    
    # Get target playlist URL
    target_playlist_id = get_playlist_url()
    if not target_playlist_id:
        print("No playlist selected. Exiting...")
        return
        
    # Verify playlist access
    if not verify_playlist_access(sp, target_playlist_id):
        print("Cannot access playlist. Make sure you have the right permissions.")
        return
    
    # Open file dialog for chat file selection
    file_path = select_chat_file()
    if not file_path:
        print("No file selected. Exiting...")
        return
    
    # Read chat content
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            chat_content = file.read()
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return
    
    print("Successfully connected to Spotify and read chat file")
    
    # Get existing tracks in the target playlist
    print("\nLoading your target playlist...")
    existing_tracks = get_playlist_tracks(sp, target_playlist_id, "Loading target playlist")
    print(f"Found {len(existing_tracks)} existing tracks in target playlist")
    
    # Extract and process Spotify links (tracks only)
    matches = extract_spotify_tracks_with_context(chat_content)
    print(f"\nFound {len(matches)} Spotify track links in chat")
    
    # Process all matches and add tracks immediately
    total_added = process_matches(sp, matches, existing_tracks, target_playlist_id)
    
    print(f"\nFinished! Added {total_added} new tracks to playlist")

if __name__ == "__main__":
    main()