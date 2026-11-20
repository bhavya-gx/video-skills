"""Portable synthetic checks for the four-second landscape intro preset."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import imageio_ffmpeg
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.agents/skills/warm-vlog-intro'


class WarmVlogPackageTests(unittest.TestCase):
    def test_public_packages_match_and_contain_no_local_media(self):
        other = ROOT / '.claude/skills/warm-vlog-intro'
        left = {p.relative_to(SKILL) for p in SKILL.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        right = {p.relative_to(other) for p in other.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        self.assertEqual(left, right)
        for relative in left:
            self.assertEqual((SKILL / relative).read_bytes(), (other / relative).read_bytes())
            self.assertNotIn(relative.suffix.lower(), {'.mp4', '.mov', '.wav', '.m4a', '.onnx', '.mkv'})
        self.assertFalse((SKILL / 'assets/local-reference.json').exists())


@unittest.skipUnless(os.environ.get('REELKIT_INTEGRATION') == '1', 'Enable synthetic rendering')
class WarmVlogRenderTests(unittest.TestCase):
    def run_command(self, arguments, success=True):
        result = subprocess.run([str(x) for x in arguments], capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def prepared_project(self, parent):
        self.assertIsNotNone(importlib.util.find_spec('numpy'), 'Install requirements-portrait.txt for intro tests')
        p = parent / 'project'
        self.run_command([sys.executable, SKILL/'scripts/create_project.py', p])
        style = json.loads((p/'style.json').read_text())
        # Rights-cleared test faces replace the unbundled licensed reference faces.
        style['font_paths'] = {'didot': str(ROOT/'assets/fonts/InstrumentSerif.ttf'),
                               'didot-italic': str(ROOT/'assets/fonts/InstrumentSerif.ttf'),
                               'helvetica': str(ROOT/'assets/fonts/InterTight.ttf')}
        style['font_indices'] = {key: 0 for key in style['font_paths']}
        (p/'style.json').write_text(json.dumps(style))
        fg = p/'media/foreground'
        (fg/'frames').mkdir(parents=True); (fg/'masks').mkdir()
        mask = Image.new('L', (320, 180)); ImageDraw.Draw(mask).rectangle((130, 45, 189, 179), fill=255)
        for f in range(1, 121):
            image = Image.new('RGB', (320,180))
            draw = ImageDraw.Draw(image); draw.rectangle((130,45,189,179), fill=(210 + f % 20,40,40))
            draw.rectangle((135,70,149,100), fill=(20,230,20))
            image.save(fg/'frames'/f'{f:04d}.png'); mask.save(fg/'masks'/f'{f:04d}.png')
        options = json.loads((p/'options.json').read_text()); o = options[0]
        o['mirror'] = True
        o['prepared_for'] = {'source': o['source'], 'in': o['in'], 'source_duration': 4.0}
        (p/'options.json').write_text(json.dumps(options))
        (p/'white-centering.json').write_text(json.dumps([{'bbox':[520,180,760,720], 'center':[640,450]}]*120))
        bgs = json.loads((p/'backgrounds.json').read_text())
        for b in bgs:
            d=p/b['folder'];d.mkdir(parents=True)
            for f in range(1,7):Image.new('RGB',(160,90),(120,120,120)).save(d/f'{f:04d}.png')
            b['prepared_for']={'input':b['input'],'source_in':b['source_in']}
        (p/'backgrounds.json').write_text(json.dumps(bgs))
        self.run_command([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i',
                          'sine=frequency=440:sample_rate=48000:duration=4','-ac','2',p/'sound.wav'])
        return p

    def test_render_mirror_occlusion_expansion_warmth_timing_and_masters(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.prepared_project(Path(folder));ff=imageio_ffmpeg.get_ffmpeg_exe()
            self.run_command([sys.executable,SKILL/'scripts/render.py','--project',p,'--check'])
            command=[sys.executable,SKILL/'scripts/render.py','--project',p,'--width','320','--name','synthetic']
            self.run_command(command)
            output=p/'renders/synthetic';report=json.loads((output/'validation.json').read_text())
            self.assertEqual(len(report),2)
            self.assertTrue(all(x['frames']==120 and x['duration']==4 and x['width']==320 and x['height']==180 for x in report))
            self.assertTrue(all(x['full_decode']=='passed' and x['audio_rate']==48000 for x in report))
            self.assertTrue((output/'candidate.mov').is_file())
            frames=[0,8,9,60,114,115,119]
            selection='+'.join(f'eq(n\\,{f})' for f in frames)
            self.run_command([ff,'-v','error','-i',output/'candidate.mp4','-vf','select='+selection,
                              '-fps_mode','vfr',output/'check-%02d.png'])
            images={f:Image.open(output/f'check-{i+1:02d}.png').convert('RGB') for i,f in enumerate(frames)}
            self.assertLess(max(images[0].getpixel((5,5))),5)
            self.assertLess(max(images[60].getpixel((5,5))),5)
            for f in [115,119]:
                for xy in [(5,5),(315,5),(5,175),(315,175)]:
                    r,g,b=images[f].getpixel(xy);self.assertGreater(r,g);self.assertGreater(g,b);self.assertGreater(b,30)
            # The asymmetric green badge starts left in source, then appears right after mirroring.
            left=images[0].crop((125,50,160,120));right=images[0].crop((160,50,195,120))
            green=lambda im:sum(g>r*1.4 and g>b*1.4 for r,g,b in im.getdata())
            self.assertGreater(green(right),100);self.assertLess(green(left),10)
            # Foreground remains opaque in front of type, and type is present outside it from frame0.
            r,g,b=images[0].getpixel((160,70));self.assertGreater(r,g*2)
            self.assertGreater(sum(min(px)>170 for px in images[0].crop((55,10,125,100)).getdata()),30)
            # Consecutive frames around a nine-frame boundary use visibly different title glyphs.
            diff=sum(abs(a-b) for a,b in zip(images[8].crop((45,10,125,85)).tobytes(),images[9].crop((45,10,125,85)).tobytes()))
            self.assertGreater(diff,1000)
            repeated=self.run_command(command,success=False);self.assertIn('exists',repeated.stderr.lower())
            for im in images.values():im.close()

    def test_changed_background_rebuilds_select_without_model_and_missing_model_is_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.prepared_project(Path(folder));ff=imageio_ffmpeg.get_ffmpeg_exe();source=p/'input/sequence.mp4';source.parent.mkdir()
            self.run_command([ff,'-v','error','-f','lavfi','-i','color=red:s=160x90:r=30:d=1',
                              '-f','lavfi','-i','color=blue:s=160x90:r=30:d=1','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
                              '-map','[v]','-c:v','libx264',source])
            bgs=json.loads((p/'backgrounds.json').read_text());bgs[0].update(input='input/sequence.mp4',source_in=1.1,source_out=0.2)
            bgs[1]['input']='input/missing.mp4'
            (p/'backgrounds.json').write_text(json.dumps(bgs))
            self.run_command([sys.executable,SKILL/'scripts/prepare.py','--project',p],success=False)
            # A completed earlier slot survives a later bad source and can be reused on retry.
            bgs=json.loads((p/'backgrounds.json').read_text())
            self.assertEqual(bgs[0]['prepared_for'],{'input':'input/sequence.mp4','source_in':1.1})
            first_cache=bgs[0]['folder'];bgs[1].update(input='input/sequence.mp4',source_in=.1)
            (p/'backgrounds.json').write_text(json.dumps(bgs))
            self.run_command([sys.executable,SKILL/'scripts/prepare.py','--project',p])
            self.assertEqual(json.loads((p/'backgrounds.json').read_text())[0]['folder'],first_cache)
            b=json.loads((p/'backgrounds.json').read_text())[0];self.assertNotIn('source_out',b)
            self.assertEqual(b['prepared_for'],{'input':'input/sequence.mp4','source_in':1.1})
            cache=Path(b['folder']);self.assertEqual(len(list(cache.glob('*.png'))),6)
            with Image.open(cache/'0001.png') as image:
                r,g,blue=image.getpixel((10,10));self.assertGreater(blue,200);self.assertLess(r,30)
            self.run_command([sys.executable,SKILL/'scripts/prepare.py','--project',p])
            options=json.loads((p/'options.json').read_text());options[0]['in']=1
            (p/'options.json').write_text(json.dumps(options))
            stale=self.run_command([sys.executable,SKILL/'scripts/render.py','--project',p,'--check'],success=False)
            self.assertIn('Foreground source changed',stale.stderr)
            failed=self.run_command([sys.executable,SKILL/'scripts/prepare.py','--project',p],success=False)
            self.assertIn('model_path',failed.stderr)
            options[0]['in']=0
            (p/'options.json').write_text(json.dumps(options))
            self.run_command([ff,'-v','error','-y','-f','lavfi','-i','sine=sample_rate=48000:duration=1','-ac','2',p/'sound.wav'])
            short=self.run_command([sys.executable,SKILL/'scripts/render.py','--project',p,'--check'],success=False)
            self.assertIn('four seconds',short.stderr)


if __name__=='__main__':unittest.main()
