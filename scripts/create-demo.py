"""Reproducible media test fixture. Captions here are supplied test text, not ASR output."""
import json
import shutil
import subprocess
from pathlib import Path

from engine.project import Store
from media.render import render
from media.tools import binary, probe

ROOT=Path(__file__).resolve().parents[1]
target=ROOT/"artifacts"/"demo";target.mkdir(parents=True,exist_ok=True)
source=target/"source.mp4"
subprocess.run([binary("ffmpeg"),"-v","error","-y","-f","lavfi","-i","testsrc2=size=960x540:rate=30:duration=10",
                "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=10",
                "-af","volume=enable='between(t,3,6)':volume=0","-c:v","libx264","-threads","2","-c:a","aac",str(source)],check=True)
store=Store(target/"workspace");p=store.create(probe(source))
p["captions"]=[{"id":"fixture-1","start":.5,"end":2.5,"text":"로컬에서 영상을 편집합니다."},
                {"id":"fixture-2","start":6.5,"end":9.5,"text":"삭제 구간에 맞춰 자막 시간을 조정합니다."}]
p["cuts"]=[{"id":"test-cut","start":3,"end":6,"enabled":True,"review":False,"kind":"manual","reason":"테스트용 무음 구간 지정 (AI 분석 아님)"}]
p["settings"].update(fontSize=64)
result=render(p,store.directory(p["id"]),lambda n,m:None)
for key,name in (("path","edited.mp4"),("srt","captions.srt"),("report","report.json")):
    shutil.copyfile(result[key],target/name)
subprocess.run([binary("ffmpeg"),"-v","error","-y","-ss","1","-i",str(target/"edited.mp4"),"-frames:v","1",str(target/"subtitle-frame.png")],check=True)
(target/"README.txt").write_text("테스트 패턴+톤의 10초 원본에서 3~6초를 잘라 7초로 출력한 실제 FFmpeg 검증물입니다. 한국어 자막은 미리 지정한 테스트 문구이며 음성 인식 결과가 아닙니다. 실제 화자/원본 제공 영상은 포함하지 않습니다.\n",encoding="utf-8")
print(target)
