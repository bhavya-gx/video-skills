#!/usr/bin/env python3
"""Prepare changed foreground/background selects; reuse unchanged local caches."""
from pathlib import Path
import argparse,json,subprocess,hashlib
import numpy as np
from PIL import Image
from media import ffmpeg, probe as inspect_media
p=argparse.ArgumentParser();p.add_argument('--project',required=True,type=Path);a=p.parse_args();R=a.project.resolve()
style=json.load(open(R/'style.json'));opts=json.load(open(R/'options.json'));bgs=json.load(open(R/'backgrounds.json'));commands=[]
if len(opts)!=1:raise SystemExit('This preset expects exactly one foreground option.')
def save_json(name,value):
 target=R/name;pending=target.with_name('.'+target.name+'.pending')
 pending.write_text(json.dumps(value,indent=2),encoding='utf-8');pending.replace(target)
def path(value):
 p=Path(value);return p if p.is_absolute() else R/p
def probe(source,start,duration):
 info=inspect_media(path(source));available=info['duration']
 if start<0 or start+duration>available+.015:raise ValueError(f'Select {start}–{start+duration}s exceeds {source} ({available}s)')
 return info
def decode(source,start,duration,count,folder):
 folder.mkdir(parents=True,exist_ok=False)
 cmd=[ffmpeg(),'-v','error','-ss',str(start),'-i',str(path(source)),'-an','-vf',f'trim=duration={duration},setpts=(PTS-STARTPTS)*{count/30/duration},fps=30,setsar=1','-frames:v',str(count),'-compression_level','2',str(folder/'%04d.png')]
 (folder/'decode-command.json').write_text(json.dumps(cmd,indent=2),encoding='utf-8')
 subprocess.run(cmd,check=True);commands.append(cmd)
 if len(list(folder.glob('*.png')))!=count:raise ValueError('Select produced too few frames; adjust the source select.')
def cache_key(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()[:12]
for o in opts:
 for legacy in ['key','clip','render_source','head_x','head_y','body_bottom','median_bbox','crop']:o.pop(legacy,None)
 spec={'source':o['source'],'in':o['in'],'source_duration':o.get('source_duration',4.)};old=path(o['folder']);cent=R/'white-centering.json'
 if o.get('prepared_for')==spec and cent.exists() and all((old/k/f'{f:04d}.png').exists() for k in ['frames','masks'] for f in range(1,121)):
  print('Reusing foreground cache');continue
 model=path(style['model_path'])
 if not model.is_file():raise SystemExit('Set model_path in style.json to a local MODNet ONNX model')
 import onnxruntime as ort
 info=probe(spec['source'],spec['in'],spec['source_duration']);d=R/'media'/('foreground-'+cache_key(spec))
 if d.exists():raise SystemExit('Incomplete/stale foreground cache exists: '+str(d)+'; choose a new project or move that generated cache aside.')
 decode(spec['source'],spec['in'],spec['source_duration'],120,d/'frames');(d/'masks').mkdir()
 cfg=ort.SessionOptions();cfg.intra_op_num_threads=4;cfg.inter_op_num_threads=1
 model=path(style['model_path'])
 if not model.exists():raise SystemExit('Missing MODNet model: '+str(model))
 session=ort.InferenceSession(str(model),sess_options=cfg,providers=['CPUExecutionProvider']);prev=None;centers=[]
 first=Image.open(d/'frames/0001.png');w,h=first.size;ratio=768/max(w,h);size=(max(32,round(w*ratio/32)*32),max(32,round(h*ratio/32)*32))
 for f in range(120):
  im=Image.open(d/'frames'/f'{f+1:04d}.png').convert('RGB').resize(size,Image.Resampling.LANCZOS);x=(np.asarray(im).astype(np.float32)/127.5-1).transpose(2,0,1)[None]
  matte=np.clip(session.run(None,{'input':x})[0][0,0],0,1)
  if prev is not None:matte=.9*matte+.1*prev
  prev=matte.copy();mask=Image.fromarray((matte*255).astype('uint8'));mask.save(d/'masks'/f'{f+1:04d}.png')
  yy,xx=np.where(np.asarray(mask.resize((1280,720),Image.Resampling.BICUBIC))>128)
  if len(xx)==0:raise ValueError(f'No subject detected at frame {f}')
  bx=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)];centers.append({'bbox':bx,'center':[(bx[0]+bx[2])/2,(bx[1]+bx[3])/2]})
  if f%30==0:print('Prepared matte',f,flush=True)
 cent.write_text(json.dumps(centers,indent=2));o.update(folder=str(d),prepared_for=spec);(d/'probe.json').write_text(json.dumps(info,indent=2))
save_json('options.json',opts)
for i,b in enumerate(bgs):
 for legacy in ['render_input','source_out','output_in','output_out']:b.pop(legacy,None)
 spec={'input':b['input'],'source_in':b['source_in']};old=path(b['folder'])
 if b.get('prepared_for')==spec and all((old/f'{f:04d}.png').exists() for f in range(1,7)):continue
 info=probe(spec['input'],spec['source_in'],.2);d=R/'media'/f'background-{i:02d}-{cache_key(spec)}'
 if d.exists():raise SystemExit('Generated background cache already exists: '+str(d))
 decode(spec['input'],spec['source_in'],.2,6,d);b.update(folder=str(d),prepared_for=spec);(d/'probe.json').write_text(json.dumps(info,indent=2))
 save_json('backgrounds.json',bgs)
save_json('backgrounds.json',bgs);save_json('prepare-commands.json',commands);print('PREPARE COMPLETE',flush=True)
