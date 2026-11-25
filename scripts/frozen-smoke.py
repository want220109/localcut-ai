"""Check the frozen Python runtime, bundled VAD, ASR imports and real render."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT/"dist-engine"/"localcut-engine"/("localcut-engine.exe" if sys.platform=="win32" else "localcut-engine")
with tempfile.TemporaryDirectory(prefix="localcut-frozen-") as temporary:
    root=Path(temporary)
    def call(action,**values):
        request={"root":str(root/"data"),"action":action,**values}
        result=subprocess.run([str(EXE)],input=json.dumps(request)+"\n",encoding="utf-8",capture_output=True,timeout=120)
        lines=[json.loads(line) for line in result.stdout.splitlines()]
        assert result.returncode==0,(result.stdout,result.stderr)
        assert lines[-1]["type"]=="result",lines
        return lines[-1]["data"]
    health=call("health")
    assert health["version"]==json.loads((ROOT/"package.json").read_text(encoding="utf-8"))["version"]
    native=call("selftest")
    assert native["asrRuntime"] and native["sileroVad"]
    source=root/"sample.mp4"
    subprocess.run([health["ffmpeg"],"-v","error","-y","-f","lavfi","-i","testsrc2=size=320x180:rate=24:duration=3",
                    "-c:v","libx264","-threads","2","-pix_fmt","yuv420p",str(source)],check=True)
    p=call("create",source=str(source))
    # No speech model is fetched by smoke tests. Visual analysis still loads native OpenCV.
    result=call("analyze",id=p["id"])
    assert result["project"]["analyzed"]
    draft=call("longformDraft",id=p["id"],targetSeconds=2)["draft"]
    assert [section["title"] for section in draft["sections"]]==["도입","본론","마무리"]
    assert draft["currentSeconds"]==3 and not draft["candidates"]
    preset=json.loads((ROOT/"subtitles"/"presets.json").read_text(encoding="utf-8"))["presets"][0]
    call("edit",id=p["id"],changes={"settings":{**preset["settings"],"subtitlePreset":preset["id"]},
                                   "captions":[{"id":"font-test","start":0,"end":2,"text":"한국어 자막 글꼴 검증"}]})
    frame=call("captionFrame",id=p["id"],draft={"id":"font-test","start":0,"end":2,"text":"한국어 자막 미리보기"})
    assert frame["image"].startswith("data:image/png;base64,iVBORw0KGgo") and frame["sourceTime"]==1
    edited=call("edit",id=p["id"],changes={"cuts":[{"id":"cut","start":1,"end":1.5,"kind":"manual","enabled":True,"review":False}]})
    clip=call("cutPreview",id=p["id"],revision=edited["project"]["revision"],cutId="cut")
    assert clip["joinAt"]==1 and clip["cutEnd"]==1.5 and clip["video"]
    result=call("render",id=p["id"])
    assert Path(result["project"]["output"]["path"]).is_file()
    log=Path(result["project"]["output"]["path"]).with_name("ffmpeg.log").read_text(encoding="utf-8")
    assert "NanumGothic-Bold.ttf" in log
    print("PASS: frozen runtime, probe, visual analysis, bundled Korean font, styled MP4 output, persistence")
