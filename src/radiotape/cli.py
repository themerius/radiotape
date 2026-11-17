"""RadioTape CLI — Record Apple Music like taping from the radio."""

import shutil

import click
import sounddevice as sd


@click.group()
def cli():
    """RadioTape — Record Apple Music like taping from the radio."""
    pass


@cli.command()
def setup():
    """Check prerequisites and print setup instructions."""
    print("RadioTape Setup Check\n")

    # Check ffmpeg
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        print(f"  ffmpeg:     found ({ffmpeg})")
    else:
        print("  ffmpeg:     NOT FOUND")
        print("              Install with: brew install ffmpeg")

    # Check BlackHole
    devices = sd.query_devices()
    blackhole = None
    for i, d in enumerate(devices):
        if "blackhole" in d["name"].lower() and d["max_input_channels"] >= 2:
            blackhole = d
            break

    if blackhole:
        print(f"  BlackHole:  found ({blackhole['name']}, {int(blackhole['default_samplerate'])} Hz)")
    else:
        print("  BlackHole:  NOT FOUND")
        print("              Install with: brew install blackhole-2ch")

    # Check for Multi-Output Device
    multi_output = any("multi" in d["name"].lower() for d in devices)

    print()
    if not ffmpeg or not blackhole:
        print("Install missing dependencies first, then run setup again.\n")
        return

    if multi_output:
        print("  Multi-Output Device: found")
    else:
        print("  Multi-Output Device: NOT FOUND (may have a custom name)")

    print()
    print("Setup instructions:")
    print("  1. Open Audio MIDI Setup (Applications > Utilities)")
    print("  2. Click '+' in the bottom-left, select 'Create Multi-Output Device'")
    print("  3. Check both 'BlackHole 2ch' and your speakers/headphones")
    print("  4. Enable 'Drift Correction' for BlackHole 2ch")
    print("  5. Go to System Settings > Sound > Output")
    print("  6. Select the Multi-Output Device as output")
    print()
    print("Note: Volume keys don't work with Multi-Output Devices.")
    print("      Adjust volume in Audio MIDI Setup instead.")
    print()
    print("Full guide: README.md → 'One-time audio setup'")
    print("            https://github.com/themerius/radiotape#one-time-audio-setup")
    print()
    print("Then run: radiotape record")


@cli.command()
def devices():
    """List available audio input devices."""
    print("Audio input devices:\n")
    all_devices = sd.query_devices()
    for i, d in enumerate(all_devices):
        if d["max_input_channels"] > 0:
            marker = " <-- use this" if "blackhole" in d["name"].lower() else ""
            print(f"  [{i}] {d['name']} ({d['max_input_channels']}ch, {int(d['default_samplerate'])} Hz){marker}")


@cli.command()
@click.option("--output-dir", "-o", default="./music", help="Output directory for recorded tracks.")
@click.option("--device", "-d", default="BlackHole 2ch", help="Audio input device name.")
@click.option("--bitrate", "-b", default="320k", help="MP3 bitrate (e.g. 128k, 256k, 320k).")
@click.option("--no-artwork", is_flag=True, help="Skip fetching album artwork.")
@click.option(
    "--split-mode",
    type=click.Choice(["position", "poll"]),
    default="position",
    show_default=True,
    help="How track boundaries are found. 'position' uses Music.app's playback "
    "position for exact cuts; 'poll' cuts when the change is noticed (legacy, "
    "may include up to ~1s of the next track).",
)
@click.option(
    "--cut-offset-ms",
    type=float,
    default=0.0,
    show_default=True,
    help="Shift cut points (position mode). Positive = later. Use to compensate "
    "for audio routing latency.",
)
@click.option("--no-snap", is_flag=True, help="Don't snap cut points to nearby silence (position mode).")
def record(
    output_dir: str,
    device: str,
    bitrate: str,
    no_artwork: bool,
    split_mode: str,
    cut_offset_ms: float,
    no_snap: bool,
):
    """Start recording from Apple Music.

    Play music in Apple Music and RadioTape will automatically split
    and save each track as a tagged MP3 file.
    """
    from .orchestrator import RecordingSession

    session = RecordingSession(
        output_dir=output_dir,
        device=device,
        bitrate=bitrate,
        artwork=not no_artwork,
        split_mode=split_mode,
        cut_offset_ms=cut_offset_ms,
        snap=not no_snap,
    )

    try:
        session.run()
    except RuntimeError as e:
        raise click.ClickException(str(e))


if __name__ == "__main__":
    cli()
