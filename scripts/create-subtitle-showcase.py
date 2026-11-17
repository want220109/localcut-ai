"""Generate actual MP4/PNG style examples. Text is supplied test text, not ASR."""
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.project import Store
from media.render import render
from media.tools import binary, probe
from subtitles.styles import PRESETS, preset_settings

target=ROOT/"artifacts"/"subtitle-styles-0.2.0";target.mkdir(parents=True,exist_ok=True)
source=target/"style-source.mp4"
subprocess.run([binary("ffmpeg"),"-v","error","-y","-f","lavfi","-i","color=c=0x14253d:size=1280x720:rate=24:duration=2",
                "-vf","drawbox=x=100:y=80:w=300:h=220:color=0x294a64:t=fill,drawbox=x=700:y=220:w=400:h=340:color=0x213b50:t=fill",
                "-c:v","libx264","-threads","2",str(source)],check=True)
store=Store(target/"workspace");images=[];filters=[];entries=[]
for index,(identifier,info) in enumerate(PRESETS.items()):
    p=store.create(probe(source))
    p["settings"].update(preset_settings(identifier))
    p["settings"].update(resolution="720",aspect=info["aspect"],highlightWords="이야기,순간",quality="high")
    p["captions"]=[{"id":"sample","start":0,"end":2,"text":"당신의 이야기가 더 선명해지는 순간"}]
    output=render(p,store.directory(p["id"]),lambda *_:None)
    import shutil
    mp4=target/(identifier+".mp4");shutil.copyfile(output["path"],mp4)
    frame=target/(identifier+".png")
    subprocess.run([binary("ffmpeg"),"-v","error","-y","-ss","1","-i",str(mp4),"-frames:v","1",str(frame)],check=True)
    images.append(frame)
    if index<2:scale,pad,labelsize="600:338","600:380:0:42",18
    else:scale,pad,labelsize="290:516","290:560:0:44",16
    filters.append(f"[{index}:v]scale={scale},pad={pad}:color=0x101820,drawtext=fontfile=assets/fonts/NanumGothic-Bold.ttf:text='{info['label']}':x=12:y=12:fontsize={labelsize}:fontcolor=white[i{index}]")
    entries.append({"preset":identifier,"label":info["label"],"mp4":mp4.name,"frame":frame.name,"report":output["report"]})
filters += ["[i0][i1]xstack=inputs=2:layout=0_0|620_0:fill=0x101820[top]",
            "[i2][i3][i4][i5]xstack=inputs=4:layout=0_0|310_0|620_0|930_0:fill=0x101820[bottom]",
            "[top][bottom]vstack=inputs=2[all]"]
args=[binary("ffmpeg"),"-v","error","-y"]
for frame in images:args += ["-i",str(frame)]
args += ["-filter_complex_threads","1","-filter_complex",";".join(filters),"-map","[all]","-frames:v","1","-threads","2",str(target/"preview.png")]
subprocess.run(args,cwd=ROOT,check=True)
(target/"examples.json").write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding="utf-8")
(target/"README.txt").write_text("실제 FFmpeg 출력으로 만든 6종 자막 샘플입니다. 화면·대본은 생성한 테스트 자료이며 음성인식 결과나 사용자 원본 영상은 아닙니다. 스타일 선택만으로 원본 영상의 화질을 개선하지는 않습니다.\n",encoding="utf-8-sig")
print(target/"preview.png")
