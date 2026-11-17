# Saved audio treatment

The saved audio treatment uses the **original opening music and its relative voice balance**, followed by the approved calmer, brighter second-half bed. No personal or reference music is distributed in the public skill.

For the local retained edit, use its separate `music.wav` and `voice.wav` when revisions require a new mix. Use `final-mix.wav` to reproduce the existing soundtrack exactly. Do not extract the full mixed audio from draft 1 and layer it under newer dialogue, which would double the voice. The retained music stem already contains the recovered mastering envelope and transitions; do not apply those a second time.

Measured opening music/voice RMS ratio before the fade: **0.2448463086**. This is a level comparison, not a 24.5% mixer knob. Different music dynamics and voice processing require listening rather than blindly multiplying samples by this value.

The reference timeline is 43.466667 seconds:

- Opening music fades down over **18.466667–20.866667**.
- The calmer, brighter track fades up over **20.866667–23.366667**.
- Voice remains the lead. Keep effects restrained. Preserve the full spoken ending.
- Target approximately **−15.1 LUFS integrated**, maximum **−1.5 dBTP**, 48 kHz stereo.

On a new script, align the change in music to the narrative turning point instead of blindly using 0:21. Start with the same roughly 2.4-second fade-out and 2.5-second fade-in and listen for a natural handoff. Do not substitute more energetic music merely because “brighter” is requested. If the exact local stems are unavailable, disclose that and obtain a suitable replacement before claiming the same soundtrack.

The reference's small pause removal used a 100 ms music splice crossfade and 3 ms voice edge fades inside a quiet region. Those values are examples of a clean join, not permission to remove every quiet sound. Inspect and listen for consonants, breaths, clicks, doubled syllables, pumping and abrupt changes. Retiming voice requires retiming picture, matte and word cues too.
