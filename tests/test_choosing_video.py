"""Synthetic checks for the standalone landscape template, with no personal media."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import imageio_ffmpeg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.agents/skills/choosing-video'


class ChoosingPackageTests(unittest.TestCase):
    def test_packages_match_without_private_assets(self):
        files = sorted(p.relative_to(SKILL) for p in SKILL.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        for relative in files:
            self.assertEqual((SKILL / relative).read_bytes(), (ROOT / '.claude/skills/choosing-video' / relative).read_bytes())
            self.assertNotIn(relative.suffix.lower(), ['.mp4', '.mov', '.wav', '.mkv', '.m4a'])
        self.assertFalse((SKILL / 'assets/local-reference.json').exists())


@unittest.skipUnless(os.environ.get('REELKIT_INTEGRATION') == '1', 'Enable synthetic rendering')
class ChoosingRenderTests(unittest.TestCase):
    def test_matte_card_timing_custom_copy_audio_and_prores(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            def run(arguments):
                result = subprocess.run([str(a) for a in arguments], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result
            for name, source, frames, codec in [
                ('assembly.mp4', 'color=c=blue:s=640x360:r=30', 40, 'libx264'),
                ('matte.mkv', 'color=black:s=512x288:r=30,drawbox=x=0:y=0:w=256:h=288:color=white:t=fill', 40, 'ffv1'),
                ('card.mp4', 'color=lime:s=100x100:r=30', 8, 'libx264'),
            ]:
                run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', source, '-frames:v', frames, '-c:v', codec, p/name])
            run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1.333334', '-ac', '2', p/'final-mix.wav'])
            values = {
                'edit-plan.json': {'frames': 40, 'duration': 40/30},
                'graphics.json': {
                    'big': [{'text': 'FOCUS', 'x': 0, 'start_frame': 0, 'end_frame': 32,
                             'parts': [{'text': 'FOCUS', 'center_x': 960, 'y': 300, 'size': 300, 'tracking': 0}],
                             'word_events': [{'text': 'FOCUS', 'start_frame': 0}]}],
                    'captions': [{'text': 'a steady caption', 'col': 1, 'start_frame': 0, 'end_frame': 24,
                                  'word_events': [{'text': 'a', 'start_frame': 0}, {'text': 'a steady caption', 'start_frame': 5}]}],
                    'mask_intervals': []},
                'broll-manifest.json': {'assets': [{'id': 'sample', 'layout': 'card', 'render_path': 'card.mp4',
                    'width': 300, 'height': 300, 'x': 1600, 'y': 50, 'start_frame': 6, 'end_frame': 14, 'frames': 8, 'edge_fade_frames': 0}]},
            }
            for name, data in values.items():
                (p/name).write_text(json.dumps(data))
            command = [sys.executable, SKILL/'scripts/render.py', '--project', p, '--width', '640',
                       '--output', p/'export.mp4', '--quality-master', p/'master.mov',
                       '--body-font', SKILL/'assets/PlayfairDisplay-variable.ttf', '--body-index', '0',
                       '--still-frames', '2', '8', '15', '39']
            run(command)
            report = json.loads((p/'export.validation.json').read_text())
            self.assertTrue(report['passed'])
            self.assertEqual([e['frames'] for e in report['exports']], [40, 40])
            self.assertTrue(all(e['size'] == [640,360] for e in report['exports']))
            frames = {i: Image.open(p/f'review/640-{i:04d}.jpg').convert('RGB') for i in [2,8,15,39]}
            self.assertGreater(frames[8].getpixel((560,40))[1], 200)
            self.assertGreater(frames[2].getpixel((560,40))[2], 200)
            self.assertGreater(frames[15].getpixel((560,40))[2], 200)
            self.assertLess(sum(1 for r,g,b in frames[8].crop((160,95,310,190)).getdata() if min(r,g,b)>220), 5)
            self.assertGreater(sum(1 for r,g,b in frames[8].crop((330,95,500,190)).getdata() if min(r,g,b)>220), 100)
            self.assertGreater(sum(1 for r,g,b in frames[8].crop((200,300,440,330)).getdata() if r>140 and g>140 and abs(r-g)<30 and r+g>1.7*b), 10)
            self.assertLess(max(frames[39].getpixel((560,40))), 5)
            audio = subprocess.run([ffmpeg, '-v', 'error', '-i', str(p/'export.mp4'), '-map', '0:a:0',
                                    '-ac', '1', '-ar', '48000', '-f', 's16le', '-'], capture_output=True, check=True).stdout
            self.assertAlmostEqual(len(audio)/96000,40/30,delta=.025)
            repeated = subprocess.run([str(a) for a in command], capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode,0)
            self.assertIn('already exists',repeated.stderr)
            for im in frames.values(): im.close()


if __name__ == '__main__':
    unittest.main()
