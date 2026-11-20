"""Small FFmpeg helpers shared by the standalone preset scripts."""
import os
from pathlib import Path
import re
import subprocess
import imageio_ffmpeg


def ffmpeg():
    return os.environ.get('REELKIT_FFMPEG') or imageio_ffmpeg.get_ffmpeg_exe()


def probe(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Media not found: {path}')
    result = subprocess.run([ffmpeg(), '-hide_banner', '-i', str(path)], capture_output=True, text=True)
    text = result.stderr
    duration = re.search(r'Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)', text)
    if not duration:
        raise ValueError(f'Cannot read media duration: {path}')
    h, m, s = map(float, duration.groups())
    video = re.search(r'Stream[^\n]*Video:[^\n]+', text)
    audio = re.search(r'Stream[^\n]*Audio:[^\n]+', text)
    dims = re.search(r'(?:, |\s)(\d{2,6})x(\d{2,6})(?:[,\s\[])', video[0]) if video else None
    fps = re.search(r'(\d+(?:\.\d+)?) fps', video[0]) if video else None
    rate = re.search(r'(\d+) Hz', audio[0]) if audio else None
    return {'duration': h * 3600 + m * 60 + s,
            'width': int(dims[1]) if dims else None, 'height': int(dims[2]) if dims else None,
            'fps': float(fps[1]) if fps else 0, 'audio_rate': int(rate[1]) if rate else None,
            'channels': (2 if 'stereo' in audio[0] else 1 if 'mono' in audio[0] else None) if audio else None,
            'has_audio': bool(audio), 'has_video': bool(video)}


def frame_count(path):
    result = subprocess.run([ffmpeg(), '-v', 'error', '-xerror', '-i', str(path), '-map', '0:v:0',
                             '-progress', 'pipe:1', '-f', 'null', '-'], capture_output=True, text=True, check=True)
    frames = re.findall(r'^frame=(\d+)$', result.stdout, re.MULTILINE)
    if not frames:
        raise ValueError('No decoded frames reported')
    return int(frames[-1])


def audio_duration(path):
    decoded = subprocess.run([ffmpeg(), '-v', 'error', '-xerror', '-i', str(path), '-map', '0:a:0',
                              '-ac', '2', '-ar', '48000', '-f', 's16le', '-'], capture_output=True, check=True)
    return len(decoded.stdout) / (48000 * 2 * 2)
