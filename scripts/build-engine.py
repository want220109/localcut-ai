import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

subprocess.run([sys.executable,"scripts/collect-notices.py"],cwd=ROOT,check=True)

args=[sys.executable,"-m","PyInstaller","--noconfirm","--clean","--onedir","--console",
      "--name","localcut-engine","--distpath","dist-engine","--workpath","build/pyinstaller",
      "--paths",str(ROOT),"--collect-all","faster_whisper","--collect-all","ctranslate2",
      "--collect-all","onnxruntime","--collect-all","scenedetect","--collect-all","av",
      "--hidden-import","engine.analysis","--hidden-import","media.render",
      "--add-data",f"{ROOT/'engine'/'styles.json'}:engine",
      "--add-data",f"{ROOT/'subtitles'/'presets.json'}:subtitles",
      "--add-data",f"{ROOT/'assets'/'fonts'}:fonts",
      "--add-data",f"{ROOT/'models'/'catalog.json'}:models","scripts/engine-entry.py"]
subprocess.run(args,cwd=ROOT,check=True)
