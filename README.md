# RadioTape

**Record Apple Music like taping from the radio.**

A Python CLI tool that captures audio from Apple Music via a virtual audio loopback device, automatically splits recordings by track, and saves tagged MP3 files — like a modern cassette deck for your Mac.

Built for the simple use case of recording a few children's albums for offline playback in the car.

## How it works

```
Apple Music plays a track
  → macOS decodes audio normally (DRM handled by Apple Music)
    → Multi-Output Device sends audio to:
        ├→ Your speakers (you hear the music)
        └→ BlackHole virtual device (RadioTape records it)
            → Automatic track splitting via Music.app metadata
            → MP3 encoding + ID3 tagging + album artwork
            → Saved to disk
```

RadioTape never touches DRM. It records the audio output — the same signal your speakers receive — like placing a tape recorder next to your stereo.

## Quick start

### Prerequisites

```bash
brew install blackhole-2ch    # virtual audio device
brew install ffmpeg            # audio encoding
```

You also need [uv](https://docs.astral.sh/uv/) (Python package manager):

```bash
brew install uv
```

### Install

```bash
git clone https://github.com/themerius/radiotape.git
cd radiotape
uv sync
```

### One-time audio setup

1. Open **Audio MIDI Setup** (Applications > Utilities)
   - If BlackHole audio device does not appear, restart audio drivers:
     `sudo killall -9 coreaudiod`
2. Click **'+'** in the bottom-left, select **"Create Multi-Output Device"**
3. Check both **BlackHole 2ch** and your speakers/headphones
4. Enable **Drift Correction** for BlackHole 2ch
5. Go to **System Settings > Sound > Output** and select the Multi-Output Device
   - Or alternative in Audio MIDI setup with right click on the device.
   - Hint: You can also record directly from BlackHole device

> Note: Volume keys don't work with Multi-Output Devices. Adjust volume in Audio MIDI Setup.

You can verify your setup:

```bash
uv run radiotape setup    # first time: runs all checks + prints these setup steps
uv run radiotape doctor   # any time: runs all checks (play a song first to test the signal)
uv run radiotape devices  # lists audio devices
```

### Checking your setup with `radiotape doctor`

`doctor` checks everything a recording depends on and tells you how to fix what's wrong. It only reads and never changes settings. (The one side effect: on first use, macOS may ask whether your terminal may control Music. That's intended, so the question doesn't pop up mid-recording.)

```
RadioTape Doctor

  ✔ ffmpeg               /opt/homebrew/bin/ffmpeg
  ✔ BlackHole            BlackHole 2ch (48000 Hz)
  ✔ Multi-Output Device  Multi-Output Device
  ✘ System output        'MacBook Pro Speakers' — audio does not reach BlackHole
                         → System Settings → Sound → Output: select the Multi-Output Device
  ✔ Music.app access     OK — playing: Interactive Noise – Angels
  ✘ Audio signal         Music.app is playing but BlackHole receives silence
                         → Route the system output through the Multi-Output Device (see 'System output')
```

| Check | What it verifies |
|---|---|
| ffmpeg | `ffmpeg` is installed (needed for MP3 encoding) |
| BlackHole | A BlackHole input device exists and runs at 48 kHz |
| Multi-Output Device | A Multi-Output (or Aggregate) Device exists |
| System output | macOS sound output goes to the Multi-Output Device / BlackHole, not directly to your speakers |
| Music.app access | RadioTape may control Music.app (macOS Automation permission) |
| Audio signal | Records 1.5 s from BlackHole: audio arrives while Music plays, and the level isn't too low. **Start a song before running `doctor`**, otherwise this check is skipped |

`✔` = OK, `!` = warning, `✘` = problem, `–` = skipped. `doctor` exits with status 1 if any check fails.

`setup` runs the same checks and then prints the one-time setup steps above.

### Record

```bash
uv run radiotape record
```

Then press play on an album in Apple Music. RadioTape detects each track change and saves individual MP3 files. Press `Ctrl+C` when done.

```bash
# Options
uv run radiotape record --output-dir ~/Music/Kids    # custom output directory
uv run radiotape record --bitrate 256k               # lower bitrate
uv run radiotape record --device "BlackHole 2ch"     # specify device
uv run radiotape record --no-artwork                 # skip artwork fetch
uv run radiotape record --split-mode poll            # legacy track splitting (fallback)
```

Output structure:

```
./music/
  Pinkfong - Baby Shark/
    01 - Baby Shark.mp3
    02 - Monkey Banana.mp3
    ...
```

Folders are named `{Album Artist} - {Album}`, falling back to the track artist when no album artist is set, so tracks with featured artists stay in the album's folder. Each MP3 is tagged with title, artist, album artist, album, track number, and album artwork (fetched from iTunes).

Run `uv run radiotape record --help` to see all options and their default values.

## Tips & troubleshooting

- **Something doesn't work? Run `radiotape doctor` while a song is playing.** It checks routing, permissions and the actual signal, and says what to fix.

- **Allow access to Music.app on first run.** macOS asks *"Terminal wants to control Music"* the first time RadioTape queries Music.app (once per terminal app, e.g. Terminal, iTerm, VS Code). Until you answer, queries hang and you'll see `Music.app did not respond within 5s`. Run `radiotape doctor` (or `setup`) once to trigger the prompt before recording. If you clicked "Don't Allow", re-enable it under System Settings → Privacy & Security → Automation.
- **Add albums to your library first.** On macOS Tahoe, Music.app scripting may not return metadata for streaming-only tracks. Click "+" or "Add to Library" on the album before recording.
- **Mute system sounds while recording.** The Multi-Output Device captures *all* system audio — including notification sounds, browser tabs, etc. Close other apps or mute notifications during recording.
- **Volume keys won't work** when using a Multi-Output Device. Adjust volume per-device in Audio MIDI Setup, or set it once before recording.
- **Switch back to normal output** when done recording. Go to System Settings > Sound > Output and select your regular speakers/headphones.
- **Track boundaries.** Track changes are detected by polling Music.app every ~1 second, but the cut itself is placed using Music.app's playback position (`playerPosition`), mapped onto the recorded audio timeline, then snapped to nearby silence (±150 ms). This gives clean cuts independent of polling latency. If cuts are consistently a little early/late on your setup, shift them with `--cut-offset-ms` (positive = later). If anything goes wrong, `--split-mode poll` restores the old behaviour (cut when the change is noticed, may include up to ~1s of the next track). `--no-snap` disables silence snapping.
- **Turn off Crossfade** in Music.app (Settings → Playback). With crossfade the tracks overlap in the audio itself, so no cut point can separate them cleanly.

## Requirements

- macOS (uses Music.app scripting + Core Audio)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.14+ (managed by uv)
- Apple Music subscription (to play the music)
- BlackHole 2ch (virtual audio device)
- ffmpeg (audio encoding)

## Legal

> **Disclaimer:** This is not legal advice. Consult an attorney for guidance on your specific situation.

### What RadioTape does — and does not do

RadioTape records the audio output of your Mac — the same signal your speakers receive. It does **not** decrypt, descramble, bypass, or interact with Apple's FairPlay DRM in any way. The DRM has already done its job: Apple Music legitimately decrypted the audio for playback. RadioTape captures what comes out the other end, like a cassette deck recording from the radio.

This distinction — capturing **post-decryption output** vs. **circumventing a protection measure** — is legally significant.

### The "analog hole" doctrine

The ability to re-capture content after legitimate decryption is known as the "analog hole" (even when the capture path is digital). It exists because DRM can only protect content up to the point of playback — once audio becomes audible, it can be re-recorded.

The [Electronic Frontier Foundation (EFF)](https://www.eff.org/issues/analog-hole) calls the analog hole "the last line of defense for fair use and more" and has actively opposed attempts to close it. In 2005, the U.S. Congress introduced the Digital Transition Content Security Act ([H.R. 4569](https://www.congress.gov/bill/109th-congress/house-bill/4569)) to require analog-to-digital conversion devices to preserve content security measures. The bill **never became law** — Congress was aware of the analog hole and chose not to close it.

### DMCA analysis (United States)

The Digital Millennium Copyright Act (DMCA), [17 U.S.C. § 1201](https://www.law.cornell.edu/uscode/text/17/1201), prohibits circumvention of technological protection measures. Specifically, to "circumvent" means:

> *"to descramble a scrambled work, to decrypt an encrypted work, or otherwise to avoid, bypass, remove, deactivate, or impair a technological measure, without the authority of the copyright owner"*

RadioTape does **none of these things**. It does not interact with FairPlay encryption. It records system audio output that has already been lawfully decrypted by the Apple Music application. [New Media Rights](https://newmediarights.org/guide/legal/copyright/dmca/How_the_DMCA_restricts_circumventing_technological_protection_measures_like_DRM_and_encryption), a nonprofit legal organization, identifies post-decryption capture as the legal path, noting it is distinct from circumvention.

**Key precedent:** In *Sony Corp. v. Universal City Studios* (1984), the U.S. Supreme Court held that private, noncommercial "time-shifting" — recording broadcast content for personal later viewing — constitutes fair use.

### Private copy exception (EU / Germany)

German copyright law, [§ 53 UrhG](https://www.gesetze-im-internet.de/englisch_urhg/englisch_urhg.html), permits natural persons to make individual copies for private use ("Privatkopie"), provided:

- The copy is from a lawful source (a paid Apple Music subscription qualifies)
- It serves no commercial purpose
- No technological protection measure is circumvented in the process

Since RadioTape captures post-decryption audio output and does not circumvent any TPM, the private copy exception likely remains intact. [§ 95a UrhG](https://www.gesetze-im-internet.de/urhg/__95a.html) (anti-circumvention) targets the act of circumventing effective technical measures — which loopback recording does not do.

### Metadata and artwork

Track metadata (title, artist, album) is fetched from the [iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html), a public, free, no-authentication API provided by Apple for developer use.

Album artwork returned by the API is classified as "Promo Content" under Apple's API terms, intended for use promoting iTunes Store content alongside an Apple badge. Embedding artwork into personal MP3 files is technically outside those terms. However, this is an extremely common practice across music players and taggers, and for personal, non-commercial, non-redistributed use the practical risk is negligible. Using the public API is also vastly preferable to scraping the Apple Music website, which Apple [explicitly prohibits](https://www.apple.com/legal/internet-services/itunes/us/terms.html).

### Apple's Terms of Service

Apple's [Media Services Terms](https://www.apple.com/legal/internet-services/itunes/us/terms.html) prohibit tampering with security technology and broadly restrict reproduction of content. Recording audio output may violate these terms.

However, a Terms of Service violation is a **breach of contract**, not copyright infringement or a criminal offense. The realistic consequence is that Apple could terminate your account. There are no known cases of Apple banning accounts for loopback recording.

### What this means in practice

| Aspect | Assessment |
|---|---|
| DRM circumvention | **No.** RadioTape does not interact with DRM. |
| DMCA § 1201 violation | **Strong argument against.** No circumvention occurs. |
| EU private copy (§ 53 UrhG) | **Likely covered** for personal, non-commercial use from a paid subscription. |
| Apple ToS | **May violate** the broad reproduction clause. Consequence: account termination (contract law). |
| Criminal risk | **Effectively zero** for personal non-commercial use. The [Protecting Lawful Streaming Act (2020)](https://en.wikipedia.org/wiki/Protecting_Lawful_Streaming_Act) targets only those who willfully provide unauthorized streaming services for commercial advantage, effectively excluding individual users. |
| Practical enforcement | **No known cases** of legal action against individuals for personal loopback recording. |

### What you must NOT do

The following would clearly create legal liability:

- **Redistribute** recorded files (torrents, file sharing, social media)
- **Commercial use** (selling recordings, using in monetized content)
- **Large-scale systematic recording** of entire catalogs
- **Share** files with others, even privately

RadioTape is for **personal use only** — recording music you're paying for, to listen to in places where streaming isn't available.

### Comparison with DRM circumvention tools

Tools like TuneFab or similar software that directly decrypt FairPlay-protected streams **do** circumvent DRM and clearly fall under DMCA § 1201. RadioTape takes a fundamentally different approach: it records system audio output without touching the protection measure.

| Approach | Circumvents DRM? | DMCA risk | Analogy |
|---|---|---|---|
| DRM removal tools | Yes | High | Picking the lock |
| **RadioTape (loopback)** | **No** | **Low** | **Recording what comes out of the speaker** |
| Buying CDs & ripping | No | None | Owning the key |

## Alternatives

### Loopback recording tools (same approach as RadioTape)

These tools capture post-decryption audio output — no DRM circumvention.

| Tool | OS | Language | Services | Auto-split | Tags | Price |
|---|---|---|---|---|---|---|
| **RadioTape** | macOS | Python | Apple Music | Yes | Yes | Free |
| [Audio Hijack](https://rogueamoeba.com/audiohijack/) | macOS | Proprietary | Any app | Yes | Yes | $69 |
| [Piezo](https://rogueamoeba.com/piezo/) | macOS | Proprietary | Any app | No | No | $29 |
| [Spytify](https://github.com/jwallet/spy-spotify) | Windows | C# | Spotify | Yes | Yes | Free |
| [SpotRec](https://github.com/Bleuzen/SpotRec) | Linux | Python | Spotify | Yes | No | Free |
| [Audials Music](https://audials.com/) | Windows | Proprietary | 10+ platforms | Yes | Yes | ~$30 |
| [Leawo Music Recorder](https://www.leawo.org/music-recorder/) | Win/Mac | Proprietary | 500+ sources | Yes | Yes | $20-30 |
| [SoundTap](https://www.nch.com.au/soundtap/) | Win/Mac | Proprietary | Any audio | No | No | ~$30 |
| [Audacity](https://www.audacityteam.org/) + [BlackHole](https://github.com/ExistentialAudio/BlackHole) | All | C++ | Any (manual) | No | No | Free |

RadioTape is the only open-source tool purpose-built for Apple Music with automatic track splitting and tagging.

### DRM circumvention tools (different approach — higher legal risk)

These tools directly decrypt or bypass DRM protection. They offer higher quality and faster downloads but clearly constitute circumvention under DMCA § 1201.

#### Apple Music

| Tool | Language | Approach | Quality | Status |
|---|---|---|---|---|
| [gamdl](https://github.com/glomatico/gamdl) | Python | Widevine CDM | AAC 256kbps (ALAC via wrapper) | Active |
| [AppleMusicDecrypt](https://github.com/WorldObservationLog/AppleMusicDecrypt) | Python | FairPlay decryption via wrapper | ALAC, Atmos, AAC | Active |
| [apple-music-downloader](https://github.com/zhaarey/apple-music-downloader) | Go | FairPlay via wrapper | ALAC, Atmos, AAC | Active |
| [Manzana](https://github.com/dropcreations/Manzana-Apple-Music-Downloader) | Python | Widevine CDM (pywidevine) | AAC only | Active |
| [TuneFab](https://www.tunefab.com/) | Proprietary | Embedded web player capture | AAC 256kbps | Commercial |
| [NoteBurner](https://www.noteburner.com/) | Proprietary | Virtual recording at 10x speed | AAC 256kbps | Commercial |
| [DRmare](https://www.drmare.com/) | Proprietary | Embedded web player capture | AAC 256kbps | Commercial |

#### Spotify

| Tool | Language | Approach | Status |
|---|---|---|---|
| [spotDL](https://github.com/spotDL/spotify-downloader) | Python | YouTube matching (no DRM bypass) | Active |
| [Zotify](https://github.com/zotify-dev/zotify) | Python | Librespot stream ripping | Stale (forks active) |
| [Sidify](https://www.sidify.com/) | Proprietary | Stream capture at 10x speed | Commercial |

#### Tidal / Deezer / Multi-service

| Tool | Language | Services | Approach | Status |
|---|---|---|---|---|
| [streamrip](https://github.com/nathom/streamrip) | Python | Qobuz, Tidal, Deezer, SoundCloud | Service APIs | Active |
| [Deemix](https://github.com/bambanah/deemix) | JS/TS | Deezer | Blowfish CBC decryption | Active (fragile) |
| [freyr-js](https://github.com/miraclx/freyr-js) | Node.js | Spotify, Apple Music, Deezer | YouTube matching | Active |
| [OrpheusDL](https://github.com/OrfiTeam/OrpheusDL) | Python | Tidal, Qobuz, Deezer, + plugins | Modular per-service APIs | Stale |
| [MediaHarbor](https://github.com/MediaHarbor/mediaharbor) | JS/Python | YouTube, Spotify, Apple Music, + | GUI wrapper for CLI tools | Active |
| [tidal-dl](https://github.com/yaronzz/Tidal-Media-Downloader) | Python | Tidal | Tidal API | Dormant |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Python | 1000+ sites | Public streams (no DRM bypass) | Very active |

#### How they compare

| Approach | Circumvents DRM? | Speed | Quality | Legal risk |
|---|---|---|---|---|
| **Loopback recording** (RadioTape) | No | Real-time | AAC 256kbps equivalent | Low |
| Widevine CDM tools (gamdl, Manzana) | Yes | Fast | AAC 256kbps | High |
| FairPlay wrapper tools (AppleMusicDecrypt) | Yes | Fast | ALAC lossless, Atmos | High |
| YouTube matching (spotDL, freyr-js) | No | Fast | Variable (YouTube source) | Low |
| Commercial converters (TuneFab, Sidify) | Yes (stream capture) | 10-35x | AAC 256kbps | High |
| Buying CDs & ripping | No | N/A | Lossless | None |

## License

MIT
