"""Stitch numbered clips (0, 1, 2, ... N) in a folder into one video.

Usage:
    python stitch.py <folder> [-o OUTPUT] [-v] [-t NAME] [-d SEC] [-k]
    python stitch.py -c   (check required software)
    python stitch.py -l   (list transitions)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

MIN_PYTHON = (3, 8)
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".flv", ".ts", ".webm", ".avi", ".m4v"}
DEFAULT_OUTPUT = "stitched.mp4"
VERTICAL_W, VERTICAL_H = 1080, 1920

# ffmpeg's xfade transitions. "none" is a hard cut.
TRANSITIONS = [
    "fade", "fadeblack", "fadewhite", "fadegrays", "dissolve", "distance",
    "wipeleft", "wiperight", "wipeup", "wipedown",
    "wipetl", "wipetr", "wipebl", "wipebr",
    "slideleft", "slideright", "slideup", "slidedown",
    "smoothleft", "smoothright", "smoothup", "smoothdown",
    "coverleft", "coverright", "coverup", "coverdown",
    "revealleft", "revealright", "revealup", "revealdown",
    "circlecrop", "rectcrop", "circleopen", "circleclose",
    "vertopen", "vertclose", "horzopen", "horzclose",
    "diagtl", "diagtr", "diagbl", "diagbr",
    "hlslice", "hrslice", "vuslice", "vdslice",
    "hlwind", "hrwind", "vuwind", "vdwind",
    "radial", "pixelize", "squeezeh", "squeezev", "zoomin",
]


def fail(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"Warning: {msg}", file=sys.stderr)


def check_requirements():
    """Return a list of problems; empty means everything is installed."""
    problems = []
    if sys.version_info < MIN_PYTHON:
        problems.append(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required (you have "
            f"{sys.version.split()[0]}).\n  Install: winget install Python.Python.3.12"
        )
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        problems.append(
            f"{' and '.join(missing)} not found on PATH.\n"
            "  Install: winget install Gyan.FFmpeg\n"
            "  Then close and reopen the terminal so PATH updates."
        )
    return problems


def find_clips(folder, output_name):
    """Return clip paths sorted by number. Warn about anything skipped."""
    clips, skipped = {}, []
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or name.lower() == output_name.lower():
            continue
        stem, ext = os.path.splitext(name)
        if not stem.isdigit() or ext.lower() not in VIDEO_EXTS:
            skipped.append(name)
            continue
        num = int(stem)
        if num in clips:
            fail(f"two clips are numbered {num}: "
                 f"{os.path.basename(clips[num])} and {name}")
        clips[num] = path

    if skipped:
        warn(f"skipping {len(skipped)} file(s) that aren't numbered video clips: "
             + ", ".join(sorted(skipped)))
    if not clips:
        fail(f"no numbered clips (0.mp4, 1.mp4, ...) found in {folder}")

    nums = sorted(clips)
    gaps = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
    if gaps:
        warn(f"missing clip number(s): {', '.join(map(str, gaps))}")
    return [clips[n] for n in nums]


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        fail(f"can't read {path}: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        fail(f"{path} has no video stream")
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    num, den = video.get("r_frame_rate", "30/1").split("/")
    return {
        "path": path,
        "duration": float(data["format"]["duration"]),
        "width": video["width"],
        "height": video["height"],
        "fps": float(num) / float(den or 1),
        "vcodec": video["codec_name"],
        "pix_fmt": video.get("pix_fmt"),
        "acodec": audio["codec_name"] if audio else None,
        "sample_rate": audio.get("sample_rate") if audio else None,
    }


def formats_match(infos):
    keys = ("width", "height", "vcodec", "pix_fmt", "acodec", "sample_rate")
    first = infos[0]
    return all(all(i[k] == first[k] for k in keys) and abs(i["fps"] - first["fps"]) < 0.01
               for i in infos)


def social_ready(info):
    """H.264 4:2:0 + AAC: what Instagram requires and YouTube/TikTok recommend."""
    return (info["vcodec"] == "h264" and info["pix_fmt"] == "yuv420p"
            and info["acodec"] in ("aac", None))


def concat_copy(infos, output):
    """Lossless join: no re-encode, nearly instant."""
    list_path = output + ".txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for info in infos:
            p = os.path.abspath(info["path"]).replace("\\", "/").replace("'", r"'\''")
            f.write(f"file '{p}'\n")
    try:
        total = sum(i["duration"] for i in infos)
        return run_ffmpeg(["-f", "concat", "-safe", "0", "-i", list_path,
                           "-c", "copy", "-movflags", "+faststart", output], total)
    finally:
        os.remove(list_path)


def build_filter(infos, vertical, transition, tdur):
    """Build the filter graph for re-encoding (crop and/or transitions)."""
    if vertical:
        w, h = VERTICAL_W, VERTICAL_H
    else:
        w, h = infos[0]["width"], infos[0]["height"]
    fps = round(infos[0]["fps"], 3)
    parts = []

    for i, info in enumerate(infos):
        norm = f"fps={fps},format=yuv420p,setsar=1"
        if vertical:
            # Full frame centred over a blurred, zoomed copy that fills 9:16.
            parts.append(
                f"[{i}:v]split[bg{i}][fg{i}];"
                f"[bg{i}]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},boxblur=20:2[bgb{i}];"
                f"[fg{i}]scale={w}:-2[fgs{i}];"
                f"[bgb{i}][fgs{i}]overlay=(W-w)/2:(H-h)/2,{norm}[v{i}]"
            )
        else:
            parts.append(
                f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,{norm}[v{i}]"
            )
        afmt = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
        if info["acodec"]:
            parts.append(f"[{i}:a]{afmt}[a{i}]")
        else:
            parts.append(f"aevalsrc=0:d={info['duration']},{afmt}[a{i}]")

    n = len(infos)
    if transition == "none" or n == 1:
        streams = "".join(f"[v{i}][a{i}]" for i in range(n))
        parts.append(f"{streams}concat=n={n}:v=1:a=1[vout][aout]")
    else:
        vprev, aprev, offset = "v0", "a0", 0.0
        for i in range(1, n):
            offset += infos[i - 1]["duration"] - tdur
            vnext = "vout" if i == n - 1 else f"vx{i}"
            anext = "aout" if i == n - 1 else f"ax{i}"
            parts.append(f"[{vprev}][v{i}]xfade=transition={transition}:"
                         f"duration={tdur}:offset={offset:.3f}[{vnext}]")
            parts.append(f"[{aprev}][a{i}]acrossfade=d={tdur}[{anext}]")
            vprev, aprev = vnext, anext
    return ";".join(parts)


def concat_reencode(infos, output, vertical, transition, tdur):
    args = []
    for info in infos:
        args += ["-i", info["path"]]
    args += [
        "-filter_complex", build_filter(infos, vertical, transition, tdur),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", output,
    ]
    total = sum(i["duration"] for i in infos)
    if transition != "none":
        total -= tdur * (len(infos) - 1)
    return run_ffmpeg(args, total)


def bar_chars():
    """Block characters if the console can show them, otherwise # and -."""
    try:
        "\u2588\u2591".encode(sys.stdout.encoding or "ascii")
        return "\u2588", "\u2591"
    except (UnicodeEncodeError, LookupError):
        return "#", "-"


BAR_CHARS = bar_chars()


def show_progress(done, total, started):
    frac = min(done / total, 1.0) if total > 0 else 0.0
    width = 30
    filled = int(frac * width)
    full, empty = BAR_CHARS
    bar = full * filled + empty * (width - filled)
    elapsed = time.monotonic() - started
    eta = f"ETA {fmt_time(elapsed / frac - elapsed)}" if frac > 0.01 else "ETA --:--"
    print(f"\r  {bar} {frac:6.1%}  {fmt_time(done)}/{fmt_time(total)}  {eta}  ",
          end="", flush=True)


def fmt_time(sec):
    sec = int(max(sec, 0))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def run_ffmpeg(args, total):
    """Run ffmpeg, drawing a progress bar from its -progress output."""
    cmd = (["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats",
            "-progress", "pipe:1", "-y"] + args)
    started = time.monotonic()
    with tempfile.TemporaryFile(mode="w+") as errors:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors,
                                stdin=subprocess.DEVNULL, text=True)
        show_progress(0, total, started)
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and value.isdigit():
                show_progress(int(value) / 1_000_000, total, started)
            elif key == "progress" and value == "end":
                show_progress(total, total, started)
        code = proc.wait()
        print()
        errors.seek(0)
        msg = errors.read().strip()
        if msg:
            print(msg, file=sys.stderr)
    return code


def main():
    parser = argparse.ArgumentParser(
        description="Stitch clips named 0, 1, 2, ... N in a folder into one video.")
    parser.add_argument("folder", nargs="?", help="folder containing the numbered clips")
    parser.add_argument("-o", "--output",
                        help=f"output file (default: {DEFAULT_OUTPUT} in the clip folder)")
    parser.add_argument("-v", "--vertical", action="store_true",
                        help="make a 9:16 (1080x1920) video with a blurred background")
    parser.add_argument("-t", "--transition", default="none", metavar="NAME",
                        help="transition between clips (default: none = hard cut); "
                             "see --list-transitions")
    parser.add_argument("-d", "--transition-duration", type=float, default=0.5, metavar="SEC",
                        help="transition length in seconds (default: 0.5)")
    parser.add_argument("-k", "--keep-format", action="store_true",
                        help="lossless join in the original format, even if it isn't "
                             "H.264 4:2:0 (e.g. OBS I444); for archive copies")
    parser.add_argument("-c", "--check", action="store_true",
                        help="only check that the required software is installed")
    parser.add_argument("-l", "--list-transitions", action="store_true",
                        help="list the available transitions")
    args = parser.parse_args()

    if args.list_transitions:
        print("none (hard cut, default)")
        print("\n".join(TRANSITIONS))
        return

    problems = check_requirements()
    if problems:
        print("Missing required software:\n", file=sys.stderr)
        print("\n\n".join(problems), file=sys.stderr)
        sys.exit(1)
    if args.check:
        print("All required software is installed.")
        return

    if not args.folder:
        parser.error("folder is required")
    if not os.path.isdir(args.folder):
        fail(f"folder not found: {args.folder}")
    if args.transition != "none" and args.transition not in TRANSITIONS:
        fail(f"unknown transition '{args.transition}'; see --list-transitions")
    if args.transition_duration <= 0:
        fail("--transition-duration must be greater than 0")

    output = args.output or os.path.join(args.folder, DEFAULT_OUTPUT)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    except OSError as e:
        fail(f"can't create the output folder: {e}")
    clips = find_clips(args.folder, os.path.basename(output))
    print(f"Found {len(clips)} clip(s): "
          + ", ".join(os.path.basename(c) for c in clips))
    infos = [probe(c) for c in clips]

    if args.transition != "none":
        shortest = min(i["duration"] for i in infos)
        if args.transition_duration >= shortest:
            fail(f"transition ({args.transition_duration}s) must be shorter than the "
                 f"shortest clip ({shortest:.2f}s)")

    needs_reencode = args.vertical or args.transition != "none"
    if not needs_reencode and not formats_match(infos):
        warn("clips have different formats; re-encoding instead of a lossless join")
        needs_reencode = True
    elif not needs_reencode and not args.keep_format and not social_ready(infos[0]):
        i = infos[0]
        warn(f"clips are {i['vcodec']} {i['pix_fmt']} / {i['acodec']}; re-encoding to "
             "H.264 4:2:0 + AAC for social media (use -k to keep the original format)")
        needs_reencode = True

    if needs_reencode:
        print("Re-encoding...")
        code = concat_reencode(infos, output, args.vertical, args.transition,
                               args.transition_duration)
    else:
        print("Joining (lossless)...")
        code = concat_copy(infos, output)

    if code != 0:
        fail(f"ffmpeg failed (exit code {code})")
    print(f"Done: {output}")


if __name__ == "__main__":
    main()
