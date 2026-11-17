"""RadioTape CLI — Record Apple Music like taping from the radio."""

import click
import sounddevice as sd


@click.group()
def cli():
    """RadioTape — Record Apple Music like taping from the radio."""
    pass


@cli.command()
@click.option("--device", "-d", default="BlackHole 2ch", help="Audio input device name.")
def doctor(device: str):
    """Check that everything needed for recording works.

    Read-only: nothing is changed. Checks ffmpeg, BlackHole, the Multi-Output
    Device, the system sound output, access to Music.app, and (while Music is
    playing) that audio actually reaches BlackHole. Exits with status 1 if a
    check fails.
    """
    from .doctor import print_checks, run_checks

    print("RadioTape Doctor\n")
    failed = print_checks(run_checks(device=device))
    if failed:
        raise SystemExit(1)


@cli.command()
def setup():
    """Run the doctor checks and print one-time setup instructions."""
    from .doctor import SETUP_DOCS, print_checks, run_checks

    print("RadioTape Setup\n")
    print_checks(run_checks())
    print()
    print("One-time setup:")
    print("  1. brew install blackhole-2ch ffmpeg")
    print("  2. Open Audio MIDI Setup (Applications > Utilities)")
    print("  3. Click '+' in the bottom-left, select 'Create Multi-Output Device'")
    print("  4. Check both 'BlackHole 2ch' and your speakers/headphones")
    print("  5. Enable 'Drift Correction' for BlackHole 2ch")
    print("  6. System Settings > Sound > Output: select the Multi-Output Device")
    print("  7. Allow your terminal to control Music.app when macOS asks")
    print()
    print("Note: Volume keys don't work with Multi-Output Devices.")
    print("      Adjust volume in Music.app or Audio MIDI Setup instead.")
    print()
    print(f"Full guide: {SETUP_DOCS}")
    print()
    print("Re-check any time with: radiotape doctor")


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
