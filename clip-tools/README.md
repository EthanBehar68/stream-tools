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
Write the timestamps in a text file, one range per line, with an optional note ([example-marks.txt](example-marks.txt) is a template):
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
stitch D:\clips -v --cam BL --cam-size 480x270      webcam (bottom-left, 480x270) in a band at the bottom
stitch D:\clips -v --cam BL --cam-size 480x270 -z wc    ...and zoom just enough to leave it out of the gameplay
stitch D:\clips --transition fade      crossfade between clips (0.5 s)
stitch D:\clips -o D:\out\short.mp4 --vertical --transition fadeblack --transition-duration 0.3
stitch D:\clips -k                     keep original format (lossless, not social-ready if I444)
stitch --list-transitions
```
Short flags: `-o` output, `-v` vertical, `-z` zoom, `-p` position, `-t` transition, `-d` transition length, `-k` keep format, `-c` check, `-l` list transitions.

With `-v`, the gameplay fills the width and sits on a blurred background; at the default zoom 1.0 it's only about a third of the height. `-z` takes any value from 1.0 to 3.0: at 2.0 the gameplay is about 63% of the height and keeps the middle half of its width. `-p left|center|right` picks which part of the width to keep.

`--cam` says where the webcam is in the recording: `TL TC TR` (top left/center/right), `CL CR` (center left/right), `BL BC BR` (bottom). `--cam-size` is its size in the recording's pixels; the box is assumed flush with those edges. The webcam is scaled to the full width (at most half the height) in a band at the bottom, and the gameplay fills the space above it.

The webcam is also part of the gameplay picture, so it shows twice unless the zoom trims it. `-z wc` picks the smallest zoom (and side) that leaves it out: about 1.35x for a 480 px webcam on the left or right in a 1920 px recording. A `TC`/`BC` webcam needs about twice that, keeping one side of it (`-p left` by default, or `-p right`). If it would need more than 3.0x, it stops and says so.

Output is always H.264 4:2:0 + AAC (Instagram requires 4:2:0; YouTube and TikTok recommend H.264), unless you pass `-k`. Clips already in that format are joined losslessly and instantly. Files that aren't numbered videos are skipped with a warning.
