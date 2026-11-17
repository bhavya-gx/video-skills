# Prepared project format

The renderer accepts a local folder. It does not run the repository's portrait renderer or automatically build the inputs below.

| File | Contract |
| --- | --- |
| `assembly.mp4` | Clean edited 16:9 picture, 30 fps, native delivery resolution, normalized SDR Rec.709; original framing. |
| `matte.mkv` | Frame-aligned subject opacity, white foreground and black background. Rendered at 512×288 and scaled with the picture; retain a better source matte for future refinements. |
| `final-mix.wav` | Complete voice/music/effects mix, at least the picture's duration. Prefer 48 kHz stereo. `--audio` overrides it. |
| `edit-plan.json` | `frames` as a positive integer, `duration = frames / 30`; retain original source ranges and output mapping as additional fields. |
| `graphics.json` | `captions`, `big`, and `mask_intervals` as described below. |
| `broll-manifest.json` | `assets`: the card entries below; an empty array is valid. |
| `style-settings.json` | Optional complete copy of bundled `assets/style.json` for project-specific colour changes. |

`assets/project-example.json` contains three named JSON objects. Save each under its key as a separate file, then replace its demonstration text and frame events with the real aligned speech. It contains no usable footage or sound. Copying it does not create a finished edit.

All intervals are half-open `[start_frame, end_frame)` and use edited output time. Source ranges remain separate. If a cut changes, recompute every dependent output frame. The renderer intentionally ignores legacy `start`/`end` seconds in text entries, because those can disagree with retimed integer frames.

## Text

Each caption needs `text`, `col` (0, 1 or 2), `start_frame`, `end_frame`, and `word_events`. Each word event contains the cumulative revealed `text` and its absolute output `start_frame`. Reveal text must be a growing prefix of the final phrase. Keep the complete phrase's anchor stable during reveals. Caption baselines and font are fixed by the saved design.

Each enlarged heading needs the same timing and `word_events`, plus `text`, a legacy `x` discriminator (use 0 for custom parts), and optionally `parts`. A part has `text`, `y`, `size`, `tracking`, and either `x` or `center_x`, all in design pixels. Parts are revealed in listed order according to the number of words in the active event. They are drawn behind the matte.

```json
{
  "text": "one thing",
  "x": 0,
  "start_frame": 45,
  "end_frame": 90,
  "parts": [
    {"text": "one thing", "center_x": 1383.57, "y": 177.49, "size": 203, "tracking": -4.36}
  ],
  "word_events": [
    {"text": "one", "start_frame": 45},
    {"text": "one thing", "start_frame": 58}
  ]
}
```

The built-in original phrase layouts use 203 px main type, 302 px hero type and 70–150 px supporting type. The larger hero uses tracking −7.67 px. Original phrases are retained in the renderer for exact local reproduction; use explicit parts for new copy.

`mask_intervals` is a historical name for the **seconds-based ranges that hide body subtitles while headlines lead**. It does not control the subject matte: the matte always occludes active enlarged headings. Each pair uses the current edited timeline and should be derived from frame boundaries / 30.

## Cards

Each entry requires `id`, `layout: "card"`, `render_path`, `x`, `y`, `width`, `height`, `start_frame`, `end_frame`, `frames` and optional `edge_fade_frames` (normally 3). `frames` must equal `end_frame - start_frame`. Prepared card files must have exactly that many decoded frames at 30 fps, with orientation and crop already applied. Render them at least as large as their intended output geometry. Their audio is discarded.

Retain `path`, `source_in`, `source_out`, `speed` and a crop/rotation record in each card's local manifest so the source/output relationship stays reviewable. Keep original media paths out of public repository examples.

## Output

The script consumes all prepared layers together and keeps the final eight-frame fade to black. New output filenames are required. It writes `<output>.validation.json` with decoded frame count, size, fps and SHA-256. Candidate files remain hidden if a render fails; inspect the error and inputs before retrying. Loudness and perceptual review are separate from structural validation.

The original project used an 8-bit RGB picture pipeline. A ProRes 10-bit output is a robust editing master; it does not add lost source bit depth. The 4K preset only preserves 4K detail when the assembly and prepared cards come from their original-resolution sources.
