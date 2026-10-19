# clip-tools

Two steps: `clip` cuts numbered clips (`0.mp4`, `1.mp4`, …) out of a stream recording, then `stitch` joins them in numerical order.

## Setup (once)
```
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```
Reopen the terminal, then check: `.\stitch.bat --check`

## Clip
Write the timestamps in a text file, one range per line, with an optional note:
```
1:02:10-1:02:45   funny fail
1:30:00+20        clutch win (start + length in seconds)
# lines starting with # are ignored
```
Times can be `1:02:10`, `2:10`, `130` or `1:02:10.5`. Then, from `D:\stream-tools\clip-tools`:
```
.\clip.bat D:\rec\stream.mkv -f D:\rec\marks.txt -o D:\clips
.\clip.bat D:\rec\stream.mkv 1:02:10-1:02:45 -o D:\clips      a range on the command line
```
- Cuts are frame-accurate and come out as H.264 4:2:0 + AAC. `--fast` is instant and lossless, but a clip can start up to ~2 s early (it cuts on keyframes).
- Keeps audio track 1. Use `-a 2` etc. for another OBS track.
- All ranges are checked before anything is cut. If the folder already has clips, it asks whether to continue the numbering, replace them, or quit.

## Stitch
In PowerShell, from `D:\stream-tools\clip-tools` (PowerShell needs the `.\`):
```
.\stitch.bat D:\clips                        lossless join -> D:\clips\stitched.mp4
.\stitch.bat D:\clips --vertical             9:16 with blurred background
.\stitch.bat D:\clips --transition fade      crossfade between clips (0.5 s)
.\stitch.bat D:\clips -o D:\out\short.mp4 --vertical --transition fadeblack --transition-duration 0.3
.\stitch.bat D:\clips -k                     keep original format (lossless, not social-ready if I444)
.\stitch.bat --list-transitions
```
Short flags: `-o` output, `-v` vertical, `-t` transition, `-d` transition length, `-k` keep format, `-c` check, `-l` list transitions.

Output is always H.264 4:2:0 + AAC (Instagram requires 4:2:0; YouTube and TikTok recommend H.264), unless you pass `-k`. Clips already in that format are joined losslessly and instantly. Files that aren't numbered videos are skipped with a warning.
