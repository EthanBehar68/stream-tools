"""Cut numbered clips (0.mp4, 1.mp4, ...) out of a stream recording.

Usage (cutclip.bat runs this; Windows already has a clip command):
    cutclip <recording> -f marks.txt [-o FOLDER] [--fast] [-a TRACK]
    cutclip <recording> 1:02:10-1:02:45 1:30:00+20 [-o FOLDER]

marks.txt has one range per line, with an optional note after it:
    1:02:10-1:02:45   funny fail
    1:30:00+20        clutch win (start + length in seconds)
    # lines starting with # are ignored
"""

import argparse
import os
import re
import sys

from stitch import VIDEO_EXTS, check_requirements, fail, probe, run_ffmpeg, warn

TIME = r"\d+(?::\d{1,2}){0,2}(?:\.\d+)?"
RANGE_RE = re.compile(rf"^\s*({TIME})\s*([-+])\s*({TIME})\s*(.*)$")


def parse_time(text):
    """'1:02:10.5', '2:10' or '130' -> seconds."""
    parts = text.split(":")
    if any(float(p) >= 60 for p in parts[1:]):
        raise ValueError(f"minutes/seconds must be under 60 in '{text}'")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + float(p)
    return seconds


def parse_range(text):
    """Return (range text, start, end, note) or raise ValueError."""
    m = RANGE_RE.match(text)
    if not m:
        first = text.split()[0] if text.split() else text
        raise ValueError(f"'{first}' is not a range (expected e.g. 1:02:10-1:02:45)")
    rtext = f"{m.group(1)}{m.group(2)}{m.group(3)}"
    start = parse_time(m.group(1))
    second = parse_time(m.group(3))
    end = start + second if m.group(2) == "+" else second
    if end <= start:
        raise ValueError(f"'{rtext}' ends before it starts")
    return rtext, start, end, m.group(4).strip()


def read_ranges(marks_file, inline):
    """Parse every range; return (entries, errors) so all mistakes are reported at once."""
    entries, errors = [], []
    if marks_file:
        try:
            with open(marks_file, encoding="utf-8-sig") as f:
                lines = f.readlines()
        except OSError as e:
            fail(f"can't read {marks_file}: {e}")
        for num, line in enumerate(lines, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                entries.append((num, f"line {num}") + parse_range(line))
            except ValueError as e:
                errors.append((num, f"line {num}: {e}"))
    # Command-line ranges sort after the file's lines.
    for num, text in enumerate(inline, len(lines) + 1 if marks_file else 1):
        try:
            entries.append((num, "command line") + parse_range(text))
        except ValueError as e:
            errors.append((num, f"command line: {e}"))
    if not entries and not errors:
        fail("no ranges given; use -f marks.txt or list ranges after the recording")
    return entries, errors


def fmt(sec):
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:04.1f}"


def existing_clips(folder):
    clips = []
    for name in os.listdir(folder):
        stem, ext = os.path.splitext(name)
        if stem.isdigit() and ext.lower() in VIDEO_EXTS:
            clips.append((int(stem), name))
    return sorted(clips)


def choose_start_number(folder):
    """If the folder already has clips, ask whether to continue or replace them."""
    clips = existing_clips(folder)
    if not clips:
        return 0
    nxt = clips[-1][0] + 1
    print(f"{folder} already has {len(clips)} numbered clip(s) "
          f"({clips[0][1]} ... {clips[-1][1]}).")
    if not sys.stdin.isatty():
        fail("not running interactively, so stopping; use an empty folder")
    while True:
        answer = input(f"  [c] continue numbering from {nxt}\n"
                       f"  [r] delete the existing clips and start from 0\n"
                       f"  [q] quit\nChoice: ").strip().lower()
        if answer == "c":
            return nxt
        if answer == "r":
            for _, name in clips:
                os.remove(os.path.join(folder, name))
            return 0
        if answer == "q":
            sys.exit(0)


def cut(recording, start, end, track, fast, output):
    audio_map = f"0:a:{track - 1}?"
    if fast:
        # Stream copy: instant and lossless, but starts at the keyframe before `start`.
        codec = ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    else:
        codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    args = (["-ss", f"{start:.3f}", "-i", recording, "-t", f"{end - start:.3f}",
             "-map", "0:v:0", "-map", audio_map] + codec
            + ["-movflags", "+faststart", output])
    return run_ffmpeg(args, end - start)


def main():
    parser = argparse.ArgumentParser(
        prog="cutclip",
        description="Cut numbered clips (0.mp4, 1.mp4, ...) out of a stream recording.")
    parser.add_argument("recording", help="the stream recording (e.g. an OBS .mkv)")
    parser.add_argument("ranges", nargs="*", metavar="RANGE",
                        help="ranges like 1:02:10-1:02:45 or 1:02:10+35")
    parser.add_argument("-f", "--file", help="text file with one range per line")
    parser.add_argument("-o", "--output", default="clips",
                        help="folder for the clips (default: clips)")
    parser.add_argument("-a", "--audio-track", type=int, default=1, metavar="N",
                        help="audio track to keep (default: 1)")
    parser.add_argument("--fast", action="store_true",
                        help="lossless instant cut; clips may start up to a "
                             "keyframe (~2 s) early")
    args = parser.parse_args()

    problems = check_requirements()
    if problems:
        print("Missing required software:\n", file=sys.stderr)
        print("\n\n".join(problems), file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.recording):
        fail(f"recording not found: {args.recording}")
    if args.audio_track < 1:
        fail("--audio-track starts at 1")

    entries, errors = read_ranges(args.file, args.ranges)
    info = probe(args.recording)
    for num, label, rtext, _, end, _ in entries:
        if end > info["duration"] + 0.05:
            errors.append((num, f"{label}: '{rtext}' ends after the recording does "
                                f"({fmt(info['duration'])})"))
    if errors:
        fail(f"{len(errors)} bad range(s), nothing was cut:\n  "
             + "\n  ".join(msg for _, msg in sorted(errors)))

    try:
        os.makedirs(args.output, exist_ok=True)
    except OSError as e:
        fail(f"can't create the output folder: {e}")
    first = choose_start_number(args.output)

    for i, (_, label, _, start, end, note) in enumerate(entries):
        name = f"{first + i}.mp4"
        desc = f" {note}" if note else ""
        print(f"[{i + 1}/{len(entries)}] {name}  {fmt(start)} - {fmt(end)}{desc}")
        if cut(args.recording, start, end, args.audio_track, args.fast,
               os.path.join(args.output, name)) != 0:
            fail(f"ffmpeg failed on {label}")
    print(f"Done: {len(entries)} clip(s) in {args.output}")


if __name__ == "__main__":
    main()
