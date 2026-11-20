#!/usr/bin/env python3
"""Create an editable copy of the saved warm intro project."""
from pathlib import Path
import argparse,json,shutil
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];dst=a.destination.resolve()
if dst.exists():raise SystemExit('Destination exists; choose a new project folder.')
shutil.copytree(root/'assets/project',dst)
model=root/'assets/models/modnet.onnx'
style=json.load(open(dst/'style.json'))
if model.exists():style['model_path']=str(model)
(dst/'style.json').write_text(json.dumps(style,indent=2))
(dst/'template-origin.json').write_text(json.dumps({'skill':str(root),'format_version':1},indent=2))
print(dst)
print('Set source selects, model_path and licensed font paths; add a four-second stereo48kHz sound.wav before preparation.')
