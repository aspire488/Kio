# HARDCODED_MEDIA — Complete Media Subsystem Inventory

## Media Manager (media_manager.py)

### Response Phrases

| Phrase | Context | Should Be External |
|---|---|---|
| "🎵 Now playing {title} by {artist}" | Successful play | YES |
| "🎵 Now playing {title}" | Successful play (no artist) | YES |
| "Music paused." | Pause action | YES |
| "Music stopped." | Stop action | YES |
| "Skipping to next track." | Skip action | YES |
| "Going back to previous track." | Previous action | YES |
| "Volume set to {level}%" | Volume change | YES |
| "No music results found for {query}" | Search failure | YES |
| "Playing {title} by {artist}" | Alternative play | YES |
| "Resuming playback." | Resume from pause | YES |
| "Music is already playing." | Already playing | YES |
| "No music is currently playing." | No active session | YES |

### Configuration Values

| Setting | Hardcoded Value | Should Be External |
|---|---|---|
| Max history entries | 500 | YES |
| Session timeout | 3600 seconds | YES |
| Volume step | 10% | YES |
| Default volume | 50% | YES |
| Crossfade duration | 0 seconds | YES |
| Gapless playback | True | YES |

### Duration Parsing

| Pattern | Regex | Legitimate |
|---|---|---|
| Seconds | `(\d+)s` | YES |
| Minutes | `(\d+)m` | YES |
| Hours | `(\d+)h` | YES |
| Combined | `(\d+)h\s*(\d+)m\s*(\d+)s` | YES |

## Media Discovery (media_discovery.py)

### Command Templates

| Provider | Command Template | Should Be External |
|---|---|---|
| YouTube search | `yt-dlp --dump-json --no-download --flat-playlist "ytsearch{count}:{query}"` | YES |
| YouTube URL | `yt-dlp --get-url --get-title "{url}"` | YES |
| YouTube download | `yt-dlp -x --audio-format mp3 -o "{output}" "{url}"` | YES |
| Spotify search | `spotifydl search "{query}"` | YES |
| Spotify download | `spotifydl "{url}" -o "{output}"` | YES |

### Search Configuration

| Setting | Hardcoded Value | Should Be External |
|---|---|---|
| Default result count | 10 | YES |
| Max result count | 50 | YES |
| Playlist item limit | 100 | YES |
| Search timeout | 30 seconds | YES |
| Download timeout | 120 seconds | YES |

### Available Check

| Provider | Check Method | Legitimate |
|---|---|---|
| YouTube | `shutil.which("yt-dlp")` | YES (runtime) |
| Spotify | `shutil.which("spotifydl")` | YES (runtime) |
| Browser | WebSocket connection check | YES (runtime) |
| Local | `os.path.exists(media_dir)` | YES (runtime) |

## Media Providers

### YouTube Provider (providers/youtube_provider.py)

| Setting | Hardcoded Value | Should Be External |
|---|---|---|
| Base URL | https://www.youtube.com | NO (API spec) |
| Search URL pattern | https://www.youtube.com/results?search_query={query} | YES |
| Watch URL pattern | https://www.youtube.com/watch?v={video_id} | YES |
| Playlist URL pattern | https://www.youtube.com/playlist?list={playlist_id} | YES |
| Audio format | mp3 | YES |
| Video quality | best | YES |
| yt-dlp flags | --dump-json, --no-download, --flat-playlist | YES |

### Spotify Provider (providers/spotify_provider.py)

| Setting | Hardcoded Value | Should Be External |
|---|---|---|
| Base URL | https://open.spotify.com | NO (API spec) |
| Track URL pattern | https://open.spotify.com/track/{track_id} | YES |
| Album URL pattern | https://open.spotify.com/album/{album_id} | YES |
| Playlist URL pattern | https://open.spotify.com/playlist/{playlist_id} | YES |
| SpotifyDL command | spotifydl | YES |

### Browser Provider (providers/browser_provider.py)

| Setting | Hardcoded Value | Should Be External |
|---|---|---|
| YouTube URL | https://youtube.com | YES |
| Play button selector | .ytp-play-button | YES |
| Next button selector | .ytp-next-button | YES |
| Prev button selector | .ytp-prev-button | YES |
| Volume selector | .ytp-volume-panel | YES |
| Time display selector | .ytp-time-display | YES |
| Title selector | .ytp-title | YES |

### Local Media Provider (providers/local_media_provider.py)

| Setting | Hardcoded Value | Should Be External |
|---|---|---|
| Supported extensions | .mp3, .wav, .flac, .ogg, .m4a, .aac | YES |
| Default media directory | ~/Music | YES |
| Scan depth | 3 levels | YES |
| Max file size | 100MB | YES |

## Media Session (media_session.py)

### State Machine

| State | Description | Legitimate |
|---|---|---|
| STOPPED | No active session | YES |
| PLAYING | Actively playing | YES |
| PAUSED | Playback paused | YES |

### Session Properties

| Property | Hardcoded Default | Should Be External |
|---|---|---|
| Volume | 50% | YES |
| Muted | False | YES |
| Shuffle | False | YES |
| Repeat | False | YES |
| Current track | None | N/A |
| Playlist | [] | N/A |
| Position | 0 | N/A |

### Session Events

| Event | Trigger | Legitimate |
|---|---|---|
| track_end | Playback complete | YES |
| error | Playback error | YES |
| state_change | State transition | YES |
| volume_change | Volume adjustment | YES |

## Media Recommender (media_recommender.py)

### Mood → Genre Mapping

| Mood | Genres | Should Be External |
|---|---|---|
| happy | pop, dance, upbeat, feel good | YES |
| relaxed | ambient, chill, lo-fi, classical | YES |
| melancholic | sad, emotional, ballad, acoustic | YES |
| energetic | rock, edm, workout, high energy | YES |
| focused | instrumental, classical, ambient, focus | YES |
| anxious | calm, soothing, nature sounds | YES |
| tired | upbeat, coffee shop, wake up | YES |

### Time-of-Day → Mood Mapping

| Time Range | Mood | Should Be External |
|---|---|---|
| 06:00-12:00 | energetic | YES |
| 12:00-17:00 | focused | YES |
| 17:00-21:00 | relaxed | YES |
| 21:00-06:00 | melancholic | YES |

### Recommendation Logic

| Factor | Weight | Hardcoded | Should Be External |
|---|---|---|---|
| Mood match | 0.4 | YES | YES |
| Time of day | 0.2 | YES | YES |
| User history | 0.3 | YES | YES |
| Popularity | 0.1 | YES | YES |

## Media Registry (media_registry.py)

### Provider Registry

| Provider | Priority | Capabilities | Hardcoded |
|---|---|---|---|
| YouTube | 1 | search, play, download | YES |
| Spotify | 2 | search, play | YES |
| Browser | 3 | play (via YouTube) | YES |
| Local | 4 | play (local files) | YES |

### Capability Mapping

| Capability | Providers | Hardcoded |
|---|---|---|
| search | YouTube, Spotify | YES |
| play | YouTube, Spotify, Browser, Local | YES |
| download | YouTube | YES |
| stream | YouTube, Spotify, Browser | YES |
| playlist | YouTube, Spotify | YES |
