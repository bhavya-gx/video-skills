# Project controls

Create a project with `scripts/create_project.py` and edit the copy. Keep media and renders in ignored local storage. The public `assets/project/` is a fill-in template.

## Foreground

`options.json` contains exactly one object:

| Field | Meaning |
| --- | --- |
| `source` | Original video path, absolute or project-relative |
| `in` | Source in-point in seconds |
| `source_duration` | Segment length fitted into four output seconds; use 4.0 for real-time motion |
| `mirror` | Horizontal flip; false preserves source orientation |
| `subject_height_1080` | Optional visible cutout height; default 908 design pixels |
| `folder` | Prepared frames/masks directory, updated by preparation |
| `prepared_for` | Source/select signature, updated by preparation |

Leave `folder` and `prepared_for` alone while changing the source select. Preparation notices changed source values, generates 120 native-resolution frames and MODNet mattes, then writes `white-centering.json`. It never changes the original video. A two-second 60 fps take may be fitted into four seconds for smooth slow motion; review any speed change.

The prepared foreground directory contains `frames/0001.png` through `0120.png` and matching grayscale `masks/`. `white-centering.json` contains 120 objects with `bbox: [left,top,right,bottom]` and `center: [x,y]`, normalized to 1280×720 coordinates. Right/bottom are exclusive. Masks and images must depict the same frame. Prepared input can bypass model inference.

Scaling uses the visible alpha bounding box, preserves image proportions and bottom-aligns the figure. Inspect whether an extended arm pulls the silhouette center away from the face. A limb clipped at the original frame boundary may not make a usable cutout. Choose another take or explicitly refine the matte/framing.

## Background montage

`backgrounds.json` has 19 slots. Set each slot's `input`, `source_in`, `id` and `mirror`. Each needs six frames / 0.2 seconds of usable video; slots can reuse a clip with different selects. Keep the slot count/order to retain the saved rhythm. Preparation writes new caches into the project's `media/` folder and updates the source signature. Prepared background folders contain `0001.png` through `0006.png`.

`timeline.json` records the default output-frame-to-slot mapping and band-height fraction. `geometry.json` stores the measured expansion. The compositor maps output frames 0–119 to reference geometry frames 0–74; the final five output frames use full height. Foreground time advances naturally. Do not confuse source in-points with the montage's final output cut times.

## Typography and grade

`style.json` controls text, five-font cycle, nine-frame interval, title bounds, cutout height, font paths/indices and global grade. The naturally proportioned title fits within 1030×500 pixels, centered at (960,390) on the 1920×1080 design canvas. Source text is white; the global grade also affects it.

`font-cues.json` records the approved schedule. If the user changes the type cycle or timing, update this record to match `style.json`. Playfair 600/400 uses the bundled variable font. `didot`, `didot-italic` and `helvetica` each have a configurable file path and collection index. Didot Regular index 0 and Italic index 1 describe the reference macOS collection; verify indices for a different licensed file.

The saved warm grade is **4160 K, mix 1, lightness preservation 1**, applied once to ungraded inputs. It is a creative preset, not a calibrated measurement of perceived warmth. Do not apply it again to an already graded reference export.

## Audio, dependencies and outputs

Provide a ready-mixed four-second stereo 48 kHz `sound.wav`. Camera audio is excluded. The public template does not contain the reference soundtrack. Do not silently choose or download replacement music.

For new masks, set `model_path` to a local MODNet ONNX file. The repository's optional portrait requirements provide NumPy and ONNX Runtime; model weights remain local. A missing model is reported before generating a new foreground cache. Missing font/media paths fail preflight rather than being replaced automatically.

`render.py` creates a new `renders/NAME/` folder and refuses to reuse it. `candidate.mp4`, optional `candidate.mov`, render-command JSON, validation/checksum JSON and encoded review frames stay together. A failed attempt may leave that generated folder for diagnosis; choose a new name after fixing the input.
