# clip-tools

Two steps: `cutclip` cuts numbered clips (`0.mp4`, `1.mp4`, …) out of a stream recording, then `stitch` joins them in numerical order.

## Setup (once per PC)
In PowerShell, in this folder:
```
powershell -ExecutionPolicy Bypass -File .\Setup.ps1
```
It adds this folder to your user PATH (no admin) and offers to install Python and ffmpeg with winget. Open a new terminal, then check: `stitch --check`. Now `cutclip` and `stitch` work from any folder. (It's `cutclip`, not `clip`: Windows already has a `clip` command that copies to the clipboard.)

Re-run it if the drive letter changes. To remove it from PATH: `.\Setup.ps1 -Uninstall`.

## Cut clips
Write the timestamps in a text file, one range per line, with an optional note:
```
1:02:10-1:02:45   funny fail
1:30:00+20        clutch win (start + length in seconds)
# lines starting with # are ignored
```
Times can be `1:02:10`, `2:10`, `130` or `1:02:10.5`. Then:
```
cutclip D:\rec\stream.mkv -f D:\rec\marks.txt -o D:\clips
cutclip D:\rec\stream.mkv 1:02:10-1:02:45 -o D:\clips      a range on the command line
```
- Cuts are frame-accurate and come out as H.264 4:2:0 + AAC. `--fast` is instant and lossless, but a clip can start up to ~2 s early (it cuts on keyframes).
- Keeps audio track 1. Use `-a 2` etc. for another OBS track.
- All ranges are checked before anything is cut. If the folder already has clips, it asks whether to continue the numbering, replace them, or quit.

## Stitch
```
stitch D:\clips                        lossless join -> D:\clips\stitched.mp4
stitch D:\clips --vertical             9:16 with blurred background
stitch D:\clips -v -z 1.8              9:16, gameplay 1.8x bigger (sides trimmed)
stitch D:\clips -v -z 2.5 -p left      zoom in on the left part of the screen
stitch D:\clips --transition fade      crossfade between clips (0.5 s)
stitch D:\clips -o D:\out\short.mp4 --vertical --transition fadeblack --transition-duration 0.3
stitch D:\clips -k                     keep original format (lossless, not social-ready if I444)
stitch --list-transitions
```
Short flags: `-o` output, `-v` vertical, `-z` zoom, `-p` position, `-t` transition, `-d` transition length, `-k` keep format, `-c` check, `-l` list transitions.

With `-v`, the gameplay fills the width and sits on a blurred background; at the default zoom 1.0 it's only about a third of the height. `-z` takes any value from 1.0 to 3.0: at 2.0 the gameplay is about 63% of the height and keeps the middle half of its width. `-p left|center|right` picks which part of the width to keep.

Output is always H.264 4:2:0 + AAC (Instagram requires 4:2:0; YouTube and TikTok recommend H.264), unless you pass `-k`. Clips already in that format are joined losslessly and instantly. Files that aren't numbered videos are skipped with a warning.
