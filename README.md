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
git clone https://github.com/simonherold/radiotape.git
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
uv run radiotape setup    # checks all prerequisites
uv run radiotape devices  # lists audio devices
```

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
```

Output structure:

```
./music/
  Pinkfong - Baby Shark/
    01 - Baby Shark.mp3
    02 - Monkey Banana.mp3
    ...
```

Each MP3 is tagged with title, artist, album, track number, and album artwork (fetched from iTunes).

Run `uv run radiotape record --help` to see all options and their default values.

## Tips & troubleshooting

- **Add albums to your library first.** On macOS Tahoe, Music.app scripting may not return metadata for streaming-only tracks. Click "+" or "Add to Library" on the album before recording.
- **Mute system sounds while recording.** The Multi-Output Device captures *all* system audio — including notification sounds, browser tabs, etc. Close other apps or mute notifications during recording.
- **Volume keys won't work** when using a Multi-Output Device. Adjust volume per-device in Audio MIDI Setup, or set it once before recording.
- **Switch back to normal output** when done recording. Go to System Settings > Sound > Output and select your regular speakers/headphones.
- **Track boundaries** are detected by polling Music.app every ~1 second. You may get up to ~0.5s of overlap between tracks — inaudible in practice.

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

## License

MIT
