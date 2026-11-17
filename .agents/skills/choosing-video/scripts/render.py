"""Render the Choosing landscape template from a locally prepared edit project."""
import argparse
import copy
import json
import math
import subprocess
from pathlib import Path

import hashlib
import uuid
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageFilter


SKILL = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project', type=Path, required=True)
parser.add_argument('--width', type=int, default=3840)
parser.add_argument('--quality-master', type=Path)
parser.add_argument('--output', type=Path)
parser.add_argument('--stills-only', action='store_true')
parser.add_argument('--still-frames', type=int, nargs='+')
parser.add_argument('--audio', type=Path)
parser.add_argument('--body-font', type=Path)
parser.add_argument('--body-index', type=int, default=10)
parser.add_argument('--headline-font', type=Path)
args = parser.parse_args()
R = args.project.resolve()
W = args.width
if W < 320 or W % 32:
    parser.error('--width must be at least 320 and a multiple of 32 for even 16:9 dimensions')
H = W * 9 // 16
scale = W / 1920
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
args.audio = (args.audio or R / 'final-mix.wav').resolve()
args.output = (args.output or R / 'choosing-export.mp4').resolve()
args.quality_master = args.quality_master.resolve() if args.quality_master else None
body_font = args.body_font or Path('/System/Library/Fonts/HelveticaNeue.ttc')
headline_font = args.headline_font or SKILL / 'assets/PlayfairDisplay-variable.ttf'
if not body_font.is_file():
    parser.error('Helvetica Neue is not available. Supply a licensed --body-font and --body-index; disclose any substitution.')
if not headline_font.is_file():
    parser.error('Missing Playfair Display font')
plan = json.loads((R / 'edit-plan.json').read_text())
graphics = json.loads((R / 'graphics.json').read_text())
manifest = json.loads((R / 'broll-manifest.json').read_text())
settings_path = R / 'style-settings.json'
settings = json.loads((settings_path if settings_path.exists() else SKILL / 'assets/style.json').read_text())
if (type(plan['frames']) is not int or plan['frames'] < 1
        or abs(plan['duration'] - plan['frames'] / 30) > 1e-6):
    parser.error('Project must use integer 30 fps frames and matching duration')
for path in [R/'assembly.mp4', R/'matte.mkv', args.audio]:
    if not path.is_file():
        parser.error(f'Missing prepared project media: {path}')
info_reader = imageio_ffmpeg.read_frames(str(R/'assembly.mp4'))
info = next(info_reader)
info_reader.close()
if abs(info['size'][0] / info['size'][1] - 16/9) > .003:
    parser.error('Assembly must be 16:9; preserve the original framing when preparing it')
if not args.stills_only and W > info['size'][0]:
    parser.error('Export width exceeds assembly resolution; rebuild from original camera media')
for item in manifest['assets']:
    if item.get('layout') != 'card':
        parser.error('This preset uses floating cards; full-screen B-roll is not enabled')
    if (item['end_frame'] - item['start_frame'] != item['frames']
            or not 0 <= item['start_frame'] < item['end_frame'] <= plan['frames']):
        parser.error(f'Invalid card interval: {item["id"]}')
for item in graphics['big'] + graphics['captions']:
    if not 0 <= item['start_frame'] < item['end_frame'] <= plan['frames']:
        parser.error('Text interval extends beyond the timeline')
    if any(not item['start_frame'] <= e['start_frame'] < item['end_frame'] for e in item['word_events']):
        parser.error('Word reveal falls outside its text interval')
review = R / 'review'
review.mkdir(exist_ok=True)
final_output, final_master = args.output, args.quality_master
validation_path = final_output.with_suffix('.validation.json')
if not args.stills_only:
    for path in [final_output, final_master, validation_path]:
        if path and path.exists():
            parser.error(f'Output already exists; choose a new filename: {path}')
    token = uuid.uuid4().hex
    for path in [final_output, final_master]:
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
    args.output = final_output.with_name(f'.{final_output.stem}-{token}.mp4')
    if final_master:
        args.quality_master = final_master.with_name(f'.{final_master.stem}-{token}.mov')

def reader(path, width, height, gray=False):
    return subprocess.Popen([FFMPEG, '-v', 'error', '-xerror', '-i', str(path), '-an', '-vf', f'fps=30:eof_action=pass,scale={width}:{height}:flags=lanczos', '-f', 'rawvideo', '-pix_fmt', 'gray' if gray else 'rgb24', '-'], stdout=subprocess.PIPE)

def font(size, kind):
    if kind=='headline':
        result=ImageFont.truetype(str(headline_font),max(1,round(size*scale)))
        result.set_variation_by_axes([600])
        return result
    return ImageFont.truetype(str(body_font),max(1,round(size*scale)),index=args.body_index)

def sprite(text, face, tracking=0):
    bounds = face.getbbox(text, anchor='ls')
    width = math.ceil(face.getlength(text) + max(0, len(text) - 1) * tracking) + 8
    image = Image.new('RGBA', (max(1, width), bounds[3] - bounds[1] + 8))
    draw = ImageDraw.Draw(image)
    for i, ch in enumerate(text):
        x = 4 + face.getlength(text[:i]) + i * tracking
        draw.text((x, -bounds[1] + 4), ch, font=face, fill=tuple(settings['lettering_rgb']) + (255,), anchor='ls')
    return image, bounds[1]

front_titles = set()  # All enlarged text passes behind the subject.

def tracked_width(text,face,tracking):
    return face.getlength(text)+max(0,len(text)-1)*tracking

def render_phrase(text,full,face,tracking,colour=None):
    box=face.getbbox(full,anchor='ls')
    width=math.ceil(tracked_width(full,face,tracking))+12
    out=Image.new('RGBA',(max(1,width),box[3]-box[1]+8))
    d=ImageDraw.Draw(out)
    for i,ch in enumerate(text):
        d.text((4-box[0]+face.getlength(text[:i])+i*tracking,4-box[1]),ch,font=face,fill=tuple(colour or settings['lettering_rgb'])+(255,),anchor='ls')
    return out

# Each fragment uses the new reference's measured nominal size/anchor palette.
# Current spoken words and entrance/exit frames stay unchanged.
def centered_part(text,center,y,size,tracking):
    face=font(size,'headline')
    rendered=render_phrase(text,text,face,tracking*scale,settings['headline_rgb'])
    box=rendered.getbbox()
    return (text,center-(box[2]-box[0])/scale/2,y,size,tracking)

def visible_height(text,size,tracking):
    rendered=render_phrase(text,text,font(size,'headline'),tracking*scale,settings['headline_rgb'])
    box=rendered.getbbox()
    return (box[3]-box[1])/scale

headings=[]
for entry in graphics['big']:
    e=copy.deepcopy(entry);txt=e['text']
    if e.get('parts'):
        parts=[]
        for part in e['parts']:
            if 'center_x' in part:
                parts.append(centered_part(part['text'],part['center_x'],part['y'],part['size'],part.get('tracking',0)))
            else:
                parts.append((part['text'],part['x'],part['y'],part['size'],part.get('tracking',0)))
    elif txt=='that’s the':parts=[('that’s',129.4,180.5,203,-4.36),('the',385.2,342.95,120,-2)]
    elif txt=='paradox':parts=[(txt,1086.39,246.69,203,-4.36)]
    elif txt=='of choice':parts=[('of',1594.98,408.08,120,-2),('choice',1282.01,483.29,150,-3)]
    elif txt=='so pick one':
        so_y=210
        pick_y=so_y+visible_height('so',203,-4.36)+32
        one_y=pick_y+visible_height('pick',203,-4.36)+30
        parts=[centered_part('so',350,so_y,203,-4.36),centered_part('pick',350,pick_y,203,-4.36),centered_part('one',350,one_y,120,-2)]
    elif txt=='dream':
        f=font(302,'headline');width=tracked_width(txt,f,-7.67*scale)/scale
        parts=[(txt,1383.57-width/2,177.49,302,-7.67)]
    elif txt=='for this one chapter':parts=[centered_part('for this one',1383.57,463.29,70,-1),centered_part('chapter',1383.57,550,120,-2)]
    elif txt=='of your life':parts=[centered_part(txt,1383.57,700,90,-1.8)]
    elif txt=='a major':parts=[(txt,129.4,180.5,120,-2)]
    elif txt=='focus' and entry['x']<500:parts=[(txt,69.22,317.38,203,-4.36)]
    elif txt=='and a minor':parts=[(txt,1086.39,180.5,90,-1.8)]
    elif txt=='focus':parts=[(txt,1086.39,317.38,203,-4.36)]
    elif txt=='start.':
        f=font(302,'headline');width=tracked_width(txt,f,-7.67*scale)/scale
        parts=[(txt,1383.57-width/2,177.49,302,-7.67)]
    else:raise ValueError(txt)
    x0=min(z[1] for z in parts);y0=min(z[2] for z in parts)
    bounds=[]
    for text,x,y,size,tracking in parts:
        f=font(size,'headline');sp=render_phrase(text,text,f,tracking*scale,settings['headline_rgb'])
        bounds.append((x,y,size,tracking,sp.size))
    sw=round(max((x-x0)*scale+w for x,y,size,tracking,(w,h) in bounds))+5
    sh=round(max((y-y0)*scale+h for x,y,size,tracking,(w,h) in bounds))+5
    e['sprites']=[]
    for event in e['word_events']:
        remain=len(event['text'].split());img=Image.new('RGBA',(sw,sh))
        for text,x,y,size,tracking in parts:
            tokens=text.split();count=min(remain,len(tokens));remain-=count
            if count:
                f=font(size,'headline');sp=render_phrase(' '.join(tokens[:count]),text,f,tracking*scale,settings['headline_rgb'])
                img.alpha_composite(sp,(round((x-x0)*scale),round((y-y0)*scale)))
        e['sprites'].append((event['start_frame'],img,0))
    e['x']=x0-4/scale;e['y']=y0-4/scale;e['font_role']='headline';e['resolved_font_size']=[z[3] for z in parts];e['parts']=parts
    headings.append(e)

captions=[]
for entry in graphics['captions']:
    e=copy.deepcopy(entry);face=font(51,'body');tracking=-.752*scale
    full=render_phrase(e['text'],e['text'],face,tracking)
    bbox=full.getbbox();ink_width=bbox[2]-bbox[0]
    anchor=[143,960,1760][e['col']]*scale
    left=anchor if e['col']==0 else anchor-ink_width/(2 if e['col']==1 else 1)
    e['x']=(left-bbox[0])/scale
    font_box=face.getbbox(e['text'],anchor='ls')
    e['y']=(967*scale+font_box[1]-4)/scale
    e['baseline_px']=967
    e['sprites']=[(event['start_frame'],render_phrase(event['text'],e['text'],face,tracking),0) for event in e['word_events']]
    outlined=[]
    for start,img,dy in e['sprites']:
        alpha=img.getchannel('A').filter(ImageFilter.GaussianBlur(1.5*scale)).point(lambda v:round(v*55/255))
        shadow=Image.new('RGBA',img.size,(0,0,0,0))
        shade=Image.new('RGBA',img.size,(0,0,0,0));shade.putalpha(alpha)
        shadow.alpha_composite(shade,(0,max(1,round(1.5*scale))))
        shadow.alpha_composite(img);outlined.append((start,shadow,dy))
    e['sprites']=outlined
    captions.append(e)
(R/'resolved-text-layout.json').write_text(json.dumps([dict(text=e['text'],x=e['x'],y=e['y'],font_role=e.get('font_role','body'),size=e.get('resolved_font_size',51),baseline=e.get('baseline_px')) for e in headings+captions],indent=2))

def state(e, frame):
    if not e['start_frame'] <= frame < e['end_frame']:
        return None
    active = [(image, dy) for start, image, dy in e['sprites'] if start <= frame]
    return active[-1] if active else None

assets = []
for entry in manifest['assets']:
    width, height = round(entry['width'] * scale), round(entry['height'] * scale)
    process = reader(R / entry['render_path'], width, height)
    raw = process.stdout.read()
    process.stdout.close()
    assert process.wait() == 0
    if len(raw) != entry['frames'] * width * height * 3:
        raise ValueError(f'Prepared card frame count does not match: {entry["id"]}')
    assets.append((entry, raw))

shade = Image.new('RGBA', (W, H))
draw = ImageDraw.Draw(shade)
for y in range(round(H * .66), H):
    draw.line((0, y, W, y), fill=(0, 0, 0, round(120 * (y / H - .66) / .34)))
mask_intervals = [(round(a * 30), round(b * 30)) for a, b in graphics['mask_intervals']]
frames_to_review = args.still_frames or [109, 110, 111, 240, 250, 267, 300, 430, 450, 480, 540, 811, 846, 873, 1303, 793, 800, 809, 818, 824, 826, 840, 850, 860, 870, 877, 29, 70, 108, 151, 210, 250, 309, 361, 420, 459, 500, 549, 584, 670, 728, 780, 1008, 1088, 1148, 1205, 1258, 1280, 20, 154, 156, 258, 283, 284, 312, 330, 366, 373, 374, 500, 555, 557, 626, 644, 645, 646, 672, 702, 703, 744, 792, 793, 810, 830, 872, 875, 876, 877, 928, 936, 937, 938, 958, 965, 980, 995, 1010, 1015, 1020, 1097, 1099, 1198, 1212, 1213, 1214, 1250, 1272, 1283, 1299, 1307]

picture = reader(R / 'assembly.mp4', W, H)
matte = reader(R / 'matte.mkv', 512, 288, True)
writer = None
if not args.stills_only:
    cmd=[FFMPEG,'-v','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate','30','-i','pipe:0','-i',str(args.audio)]
    cmd+=['-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','medium' if W>=1920 else 'fast','-crf','12' if W>=1920 else '21','-threads','4','-c:a','aac','-b:a','320k','-ar','48000','-ac','2','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-frames:v',str(plan['frames']),'-t',str(plan['duration']),'-movflags','+faststart',str(args.output)]
    if args.quality_master:
        cmd+=['-map','0:v:0','-map','1:a:0','-c:v','prores_ks','-profile:v','3','-vendor','apl0','-pix_fmt','yuv422p10le','-threads','3','-c:a','pcm_s24le','-ar','48000','-ac','2','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-frames:v',str(plan['frames']),'-t',str(plan['duration']),str(args.quality_master)]
    writer=subprocess.Popen(cmd,stdin=subprocess.PIPE)


for frame in range(plan['frames']):
    raw = picture.stdout.read(W * H * 3)
    maskraw = matte.stdout.read(512 * 288)
    assert len(raw) == W * H * 3 and len(maskraw) == 512 * 288, frame
    if args.stills_only and frame not in frames_to_review:
        continue
    base = Image.frombytes('RGB', (W, H), raw)
    full_active = False
    for e, frames in assets:
        if e['layout'] == 'full' and e['start_frame'] <= frame < e['end_frame']:
            full_active = True
            raise ValueError('Full-screen inserts are not part of this preset')
            break
    image = base.copy()
    behind, front = [], []
    for e in headings:
        active = state(e, frame)
        if active:
            (front if e['text'] in front_titles else behind).append((e, active))
    for e, (text_image, dy) in behind:
        image.paste(text_image, (round(e['x'] * scale), round(e['y'] * scale) + dy), text_image)
    if behind:
        mask = Image.frombytes('L', (512, 288), maskraw).resize((W, H), Image.Resampling.BILINEAR)
        image = Image.composite(base, image, mask)
    for e, (text_image, dy) in front:
        image.paste(text_image, (round(e['x'] * scale), round(e['y'] * scale) + dy), text_image)
    for e, frames in assets:
        if e['layout'] == 'card' and not full_active and e['start_frame'] <= frame < e['end_frame']:
            cw,ch=round(e['width']*scale),round(e['height']*scale)
            stride=cw*ch*3;offset=(frame-e['start_frame'])*stride
            card = Image.frombytes('RGB',(cw,ch),frames[offset:offset+stride])
            fade = e.get('edge_fade_frames', 0)
            alpha = min(1, (frame - e['start_frame'] + 1) / (fade + 1), (e['end_frame'] - frame) / (fade + 1)) if fade else 1
            image.paste(card, (round(e['x'] * scale), round(e['y'] * scale)), Image.new('L', card.size, round(alpha * 255)))
    if not any(start <= frame < end for start, end in mask_intervals):
        for e in captions:
            active = state(e, frame)
            if active:
                text_image, dy = active
                image.paste(text_image, (round(e['x'] * scale), round(e['y'] * scale) + dy), text_image)
    if frame >= plan['frames'] - 8:
        image = Image.blend(image, Image.new('RGB', (W, H), 'black'), (frame - (plan['frames'] - 8) + 1) / 8)
    if writer:
        writer.stdin.write(image.tobytes())
    if frame in frames_to_review:
        image.save(review / f'{W}-{frame:04d}.jpg', quality=95)
    if frame % 300 == 0:
        print(f'Render {W}: {frame}/{plan["frames"]}', flush=True)

picture.stdout.close()
matte.stdout.close()
assert picture.wait() == matte.wait() == 0
if writer:
    writer.stdin.close()
    assert writer.wait() == 0
if writer:
    reports=[]
    for path in [args.output,args.quality_master]:
        if path is None:continue
        result=subprocess.run([FFMPEG,'-v','error','-xerror','-i',str(path),'-map','0:v:0','-map','0:a:0','-progress','pipe:1','-nostats','-f','null','-'],capture_output=True,text=True)
        if result.returncode or result.stderr.strip():
            raise RuntimeError('Export failed full decode: '+result.stderr[-2000:])
        decoded=[int(line.split('=',1)[1]) for line in result.stdout.splitlines() if line.startswith('frame=')]
        if not decoded or decoded[-1] != plan['frames']:
            raise RuntimeError('Export frame count differs from the timeline')
        video=imageio_ffmpeg.read_frames(str(path));meta=next(video);video.close()
        if tuple(meta['size']) != (W,H) or abs(meta['fps']-30) > .001:
            raise RuntimeError('Export dimensions or frame rate are incorrect')
        audio_check=subprocess.run([FFMPEG,'-v','error','-i',str(path),'-map','0:a:0','-ac','1','-ar','48000','-f','s16le','-'],capture_output=True,check=True)
        if abs(len(audio_check.stdout)/96000-plan['duration']) > .04:
            raise RuntimeError('Export audio duration differs from the timeline')
        with path.open('rb') as handle:
            digest=hashlib.sha256()
            for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
            checksum=digest.hexdigest()
        reports.append({'file':str(final_output if path==args.output else final_master),
                        'frames':decoded[-1],'size':[W,H],'fps':30,'full_decode':True,'sha256':checksum})
    for source,destination in [(args.output,final_output),(args.quality_master,final_master)]:
        if source:
            if destination.exists():raise ValueError('Output appeared during render; refusing to overwrite')
            source.rename(destination)
    validation_path.write_text(json.dumps({'passed':True,'exports':reports},indent=2)+'\n')
print('Finished', final_output if writer else 'review stills', flush=True)
