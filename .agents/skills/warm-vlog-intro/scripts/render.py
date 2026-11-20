from pathlib import Path
import json,sys,subprocess,bisect,argparse,hashlib
import numpy as np
from media import ffmpeg, probe, frame_count, audio_duration
from PIL import Image,ImageOps,ImageDraw,ImageFilter,ImageFont
parser=argparse.ArgumentParser(description='Render the saved four-second warm vlog intro')
parser.add_argument('--project',required=True,type=Path)
parser.add_argument('--draft',action='store_true')
parser.add_argument('--width',type=int,help='Optional16:9 width, at least320 and a multiple of32')
parser.add_argument('--stills',action='store_true')
parser.add_argument('--frames',default='0,30,60,90,119')
parser.add_argument('--check',action='store_true')
parser.add_argument('--name')
args=parser.parse_args();R=args.project.resolve();DRAFT=args.draft;STILLS=args.stills
STYLE=json.load(open(R/'style.json'))
if args.name and (Path(args.name).name!=args.name or args.name in {'.','..'} or '/' in args.name or '\\' in args.name):parser.error('--name must be a single folder name')
def local(value):
 p=Path(value);return p if p.is_absolute() else R/p
options=json.load(open(R/'options.json'));BG=json.load(open(R/'backgrounds.json'))
if len(options)!=1:parser.error('Exactly one foreground option is required')
if len(BG)!=19:parser.error('Keep the19background slots to preserve the saved timing')
OP=options[0]
errors=[]
if not isinstance(STYLE['font_interval_frames'],int) or STYLE['font_interval_frames']<1:errors.append('font_interval_frames must be a positive integer')
if not STYLE['text'].strip():errors.append('Title text must not be empty')
if not STYLE['font_cycle'] or set(STYLE['font_cycle'])-{'playfair600','playfair400','didot','didot-italic','helvetica'}:errors.append('Unsupported font cycle')
for path in [R/'sound.wav',R/'white-centering.json',R/'geometry.json',R/'fonts/PlayfairDisplay-variable.ttf',local(STYLE['font_paths']['didot']),local(STYLE['font_paths']['didot-italic']),local(STYLE['font_paths']['helvetica'])]:
 if not path.is_file():errors.append(str(path))
if (R/'sound.wav').is_file():
 audio=probe(R/'sound.wav')
 if abs(audio['duration']-4)>.03 or audio['audio_rate']!=48000 or audio['channels']!=2:errors.append('sound.wav must be four seconds of stereo48kHz audio')
if (R/'white-centering.json').is_file():
 centers=json.load(open(R/'white-centering.json'))
 if len(centers)<120 or any(len(c['bbox'])!=4 or c['bbox'][2]<=c['bbox'][0] or c['bbox'][3]<=c['bbox'][1] for c in centers[:120]):errors.append('Invalid foreground centering; run prepare.py')
expected={'source':OP['source'],'in':OP['in'],'source_duration':OP.get('source_duration',4.)}
if OP.get('prepared_for')!=expected:errors.append('Foreground source changed: run prepare.py first')
for kind in ['frames','masks']:
 for f in range(1,121):
  p=local(OP['folder'])/kind/f'{f:04d}.png'
  if not p.is_file():errors.append(str(p))
for b in BG:
 if b.get('prepared_for')!={'input':b['input'],'source_in':b['source_in']}:errors.append('Background source changed: '+b['id'])
 for f in range(1,7):
  p=local(b['folder'])/f'{f:04d}.png'
  if not p.is_file():errors.append(str(p))
if errors:raise SystemExit('Missing or stale inputs; run prepare.py.\n'+'\n'.join(errors[:12]))
if args.check:
 print(json.dumps({'ready':True,'frames':120,'background_slots':len(BG),'grade':STYLE['grade']}));sys.exit()

W=args.width or (1280 if DRAFT else 3840)
if W<320 or W%32:parser.error('--width must be at least320 and divisible by32')
H=W*9//16;K=W/1920;S=H/1280;N=120
OPEN_END=120
D=R/'renders'/(args.name or ('stills' if STILLS else 'draft' if DRAFT else 'master'));D.mkdir(parents=True,exist_ok=False);REV=D/'review';REV.mkdir()
SOURCE=local(OP['folder']);GEO=json.load(open(R/'geometry.json'));CENTER=json.load(open(R/'white-centering.json'))
CYCLE=[0,2,4,6,8,10,12,14,16,18,20,23,25,27,30,32,34]
starts=sorted(set([2]+[b+c for b in [-24,12,47,83] for c in CYCLE if 2<=b+c<115]+[114]))
FONT_CYCLE=STYLE['font_cycle']
TITLE_CUES=[(f,FONT_CYCLE[(f//STYLE['font_interval_frames'])%len(FONT_CYCLE)]) for f in range(0,N,STYLE['font_interval_frames'])]
# The headline family and supporting faces already used in this project.
TITLES={}
FONT_SPECS={
 'playfair600':(str(R/'fonts/PlayfairDisplay-variable.ttf'),0,600),
 'playfair400':(str(R/'fonts/PlayfairDisplay-variable.ttf'),0,400),
 'didot':(str(local(STYLE['font_paths']['didot'])),STYLE['font_indices']['didot'],None),
 'didot-italic':(str(local(STYLE['font_paths']['didot-italic'])),STYLE['font_indices']['didot-italic'],None),
 'helvetica':(str(local(STYLE['font_paths']['helvetica'])),STYLE['font_indices']['helvetica'],None)
}
for name,(path,index,weight) in FONT_SPECS.items():
 def face(size):
  font=ImageFont.truetype(path,size,index=index)
  if weight:font.set_variation_by_axes([weight])
  return font
 nominal=round(600*K);font=face(nominal);b=font.getbbox(STYLE['text'])
 factor=min(STYLE['title_ink_width_1080']*K/(b[2]-b[0]),STYLE['title_ink_height_1080']*K/(b[3]-b[1]));font=face(round(nominal*factor));b=font.getbbox(STYLE['text'])
 a=Image.new('RGBA',(b[2]-b[0]+12,b[3]-b[1]+12));ImageDraw.Draw(a).text((6-b[0],6-b[1]),STYLE['text'],font=font,fill='white');a=a.crop(a.getbbox())
 layer=Image.new('RGBA',(W,H));layer.alpha_composite(a,(round((W-a.width)/2),round(STYLE['title_center_y_1080']*K-a.height/2)));TITLES[name]=layer
 title_folder=D/'titles';title_folder.mkdir(exist_ok=True);layer.save(title_folder/(name+'.png'))
def horizontal_blur(image,kernel):
 arr=np.asarray(image);left=kernel//2;right=kernel-1-left
 padded=np.pad(arr,((0,0),(left,right),(0,0)),mode='reflect')
 sums=np.cumsum(padded,axis=1,dtype=np.int32)
 sums=np.concatenate([np.zeros((arr.shape[0],1,3),dtype=np.int32),sums],axis=1)
 return Image.fromarray(np.rint((sums[:,kernel:]-sums[:,:-kernel])/kernel).clip(0,255).astype('uint8'))

def cover(src,w,h,anchor=(.5,.5)):
 scale=max(w/src.width,h/src.height);nw,nh=round(src.width*scale),round(src.height*scale);src=src.resize((nw,nh),Image.Resampling.LANCZOS)
 x=max(0,min(nw-w,round(nw*anchor[0]-w/2)));y=max(0,min(nh-h,round(nh*anchor[1]-h/2)))
 return src.crop((x,y,x+w,y+h))

def subject(f,r):
 a=Image.open(SOURCE/'frames'/f'{f+1:04d}.png').convert('RGBA')
 if DRAFT:a.thumbnail((1920,1920),Image.Resampling.LANCZOS)
 ow,oh=a.size
 mask=Image.open(SOURCE/'masks'/f'{f+1:04d}.png').convert('L').resize(a.size,Image.Resampling.BICUBIC)
 alpha=np.clip((np.asarray(mask,dtype=np.float32)-18)/220,0,1)*255;a.putalpha(Image.fromarray(alpha.astype('uint8')))
 bx=CENTER[f]['bbox'];cx=CENTER[f]['center'][0]*(ow/1280)
 scale=(OP.get('subject_height_1080',STYLE['subject_height_1080'])*K)/((bx[3]-bx[1])*(oh/720))
 if OP.get('mirror',False):a=ImageOps.mirror(a);cx=ow-cx
 a=a.resize((round(ow*scale),round(oh*scale)),Image.Resampling.LANCZOS)
 # Center the visible silhouette and bottom-align without distorting it.
 xy=(round(W/2-cx*scale),H-round(bx[3]*(oh/720)*scale))
 flash={3:1.,4:.5,7:.45,8:1.,9:.65,12:.35}.get(r,0)
 if flash:
  white=Image.new('RGBA',a.size,'white');white.putalpha(a.getchannel('A'));a=Image.blend(a,white,flash)
 return a,xy

def edge_mask(w,h,f):
 m=Image.new('L',(w,h));d=ImageDraw.Draw(m);radius=round((8 if f<75 else 8+22*min(1,(f-75)/15))*S)
 d.rounded_rectangle((0,0,w-1,h-1),radius=min(max(1,radius),h//2),fill=255)
 return m.filter(ImageFilter.GaussianBlur(max(.6,2*S)))

def frame(f):
 if not 0<=f<N:raise ValueError('Frame outside four-second opening')
 im=Image.new('RGB',(W,H),'black')
 r=round(f*74/(OPEN_END-1))
 if r>=72:r=74
 if r>=2:
  j=max(0,bisect.bisect_right(starts,r)-1);start=starts[j];end=starts[j+1] if j+1<len(starts) else 115
  b=BG[j%len(BG)];a=Image.open(local(b['folder'])/f'{min(r-start+1,6):04d}.png').convert('RGB')
  if b.get('mirror',False):a=ImageOps.mirror(a)
  full_height=GEO[72]['bottom']-GEO[72]['top']
  height=max(1,min(H,round((GEO[r]['bottom']-GEO[r]['top'])/full_height*H)))
  top=(H-height)//2;inset=0;width=W;plate_h=H
  plate=cover(a,width,plate_h);band=plate.crop((0,(plate_h-height)//2,width,(plate_h-height)//2+height))
  if r==end-1 and r<92:
   kernel=max(3,round(70*S));band=horizontal_blur(band,kernel)
  if height==H:im.paste(band,(0,0))
  else:im.paste(band,(inset,top),edge_mask(width,height,r))
 name=next(name for start,name in reversed(TITLE_CUES) if f>=start);t=TITLES[name];im.paste(t,(0,0),t)
 a,xy=subject(f,r);im.paste(a,xy,a)
 return im

review_frames=sorted(set([0,8,9,17,18,26,27,35,36,45,54,63,72,81,90,99,108,115,116,117,119]))
if STILLS:
 for f in [int(x) for x in args.frames.split(',')]:
  im=frame(f);subprocess.run([ffmpeg(),'-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-i','pipe:0','-vf',STYLE['grade'],'-frames:v','1',str(REV/f'{f:03d}.png')],input=im.tobytes(),check=True)
 print('Stills complete',flush=True);sys.exit()
base=[ffmpeg(),'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r','30','-i','pipe:0','-i',str(R/'sound.wav')]
common=['-map','0:v:0','-map','1:a:0','-vf',STYLE['grade'],'-t','4','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart']
if DRAFT:
 cmd=base+common+['-c:v','libx264','-threads','4','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','256k',str(D/'candidate.mp4')]
else:
 cmd=base+common+['-c:v','prores_ks','-threads','4','-profile:v','5','-qscale:v','1','-pix_fmt','yuv444p10le','-vendor','apl0','-c:a','pcm_s24le',str(D/'candidate.mov')]+common+['-c:v','libx264','-threads','4','-preset','slow','-crf','10','-pix_fmt','yuv420p','-c:a','aac','-b:a','320k',str(D/'candidate.mp4')]
(D/'render-command.json').write_text(json.dumps(cmd,indent=2));p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
for f in range(N):
 im=frame(f);p.stdin.write(im.tobytes())
 if f%30==0:print('Rendered',f,'/',N,flush=True)
p.stdin.close()
if p.wait():raise RuntimeError('Encoder failed')
files=[D/'candidate.mp4']+([] if DRAFT else [D/'candidate.mov']);checks=[]
for pth in files:
 info=probe(pth);count=frame_count(pth);audio_seconds=audio_duration(pth)
 if (info['width'],info['height'],count)!=(W,H,120):raise RuntimeError('Invalid output dimensions or frame count')
 if abs(info['fps']-30)>.01 or info['audio_rate']!=48000 or info['channels']!=2 or abs(audio_seconds-4)>.03 or abs(info['duration']-4)>.02:raise RuntimeError('Invalid output timing or audio rate')
 h=hashlib.sha256()
 with pth.open('rb') as inp:
  for chunk in iter(lambda:inp.read(8*1024*1024),b''):h.update(chunk)
 checks.append({'file':str(pth),'sha256':h.hexdigest(),'frames':120,'duration':4,'width':W,'height':H,'full_decode':'passed','audio_rate':48000,'audio_duration':audio_seconds,'audio_channels':2})
(D/'validation.json').write_text(json.dumps(checks,indent=2))
select='+'.join('eq(n\\,'+str(f)+')' for f in [0,30,60,90,119])
subprocess.run([ffmpeg(),'-v','error','-i',str(D/'candidate.mp4'),'-vf','select='+select+',scale=1280:720','-fps_mode','vfr','-q:v','2',str(REV/'%02d.jpg')],check=True)
print('RENDER COMPLETE',D,flush=True)
