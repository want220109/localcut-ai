import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from engine.analysis import silence_ranges, visual_analysis
from engine.project import Store
from engine.service import dispatch
from media.render import render
from media.tools import binary, probe


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    directory=tmp_path_factory.mktemp("실제 영상 한글 경로")
    filename=directory/"원본 '영상.mp4"
    subprocess.run([binary("ffmpeg"),"-v","error","-y","-f","lavfi","-i","testsrc2=size=320x180:rate=24:duration=8",
                    "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=8",
                    "-vf","drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='between(t,4,6)'",
                    "-af","volume=enable='between(t,2,4)':volume=0","-c:v","libx264","-threads","2","-pix_fmt","yuv420p","-c:a","aac",str(filename)],check=True)
    return filename


@pytest.mark.integration
def test_real_cut_burned_korean_subtitles_and_source_unchanged(tmp_path,sample):
    original_hash=hashlib.sha256(sample.read_bytes()).hexdigest()
    store=Store(tmp_path)
    p=store.create(probe(sample))
    p["captions"]=[{"id":"a","start":.5,"end":1.5,"text":"안녕하세요. 원본 영상입니다."},
                   {"id":"b","start":5,"end":7,"text":"편집 후에도 자막과 음성이 동기화됩니다."}]
    p["cuts"]=[{"id":"cut","start":2,"end":4,"enabled":True,"review":False,"kind":"manual","reason":"검증"}]
    p["settings"].update(resolution="source",fontSize=64)
    progress=[]
    p["output"]=render(p,store.directory(p["id"]),lambda n,m:progress.append(n))
    store.save(p)
    output=probe(p["output"]["path"])
    assert abs(output["duration"]-6)<.12
    assert output["codec"]=="h264" and output["hasAudio"]
    assert "00:00:03,000 --> 00:00:05,000" in Path(p["output"]["srt"]).read_text(encoding="utf-8-sig")
    assert progress[-1]==100
    assert hashlib.sha256(sample.read_bytes()).hexdigest()==original_hash
    # Full decode catches corrupted/truncated video and audio, not merely container metadata.
    subprocess.run([binary("ffmpeg"),"-v","error","-xerror","-i",output["path"],"-f","null","-"],check=True)
    result=dispatch({"root":str(tmp_path),"action":"get","id":p["id"]})
    assert result["project"]["output"]["path"]==p["output"]["path"]
    streams=json.loads(subprocess.check_output([binary("ffprobe"),"-v","error","-show_streams","-of","json",output["path"]]))["streams"]
    video=next(s for s in streams if s["codec_type"]=="video")
    audio=next(s for s in streams if s["codec_type"]=="audio")
    assert abs(float(video["duration"])-float(audio["duration"]))<.08


@pytest.mark.integration
def test_silence_and_scenes_are_measured(sample):
    source=probe(sample)
    silences=silence_ranges(str(sample),source["duration"])
    assert any(a<2.2 and b>3.8 for a,b in silences)
    scenes,motion=visual_analysis(str(sample),source["duration"],lambda *_:None)
    assert any(abs(s-4)<1 for s in scenes)
    assert len(motion)>10


@pytest.mark.integration
def test_audio_analysis_requires_model_instead_of_claiming_silence_only_ai(tmp_path,sample):
    p=dispatch({"root":str(tmp_path),"action":"create","source":str(sample)})
    with pytest.raises(ValueError,match="음성 모델"):
        dispatch({"root":str(tmp_path),"action":"analyze","id":p["id"],"model":"small"})
    assert not Store(tmp_path).load(p["id"])["analyzed"]


@pytest.mark.integration
def test_silent_video_analysis_render_and_vertical_export(tmp_path,sample):
    silent=tmp_path/"무음.mov"
    subprocess.run([binary("ffmpeg"),"-v","error","-y","-i",str(sample),"-an","-c:v","copy",str(silent)],check=True)
    p=dispatch({"root":str(tmp_path/"data"),"action":"create","source":str(silent)})
    result=dispatch({"root":str(tmp_path/"data"),"action":"analyze","id":p["id"]})
    p=result["project"]
    assert p["analyzed"] and p["cuts"]==[] and p["warnings"]
    p["settings"].update(aspect="9:16")
    result=render(p,Store(tmp_path/"data").directory(p["id"]),lambda *_:None)
    out=probe(result["path"])
    assert not out["hasAudio"] and abs(out["width"]/out["height"]-9/16)<.01


def test_source_changes_are_detected(tmp_path,sample):
    source=tmp_path/"copy.mp4";source.write_bytes(sample.read_bytes())
    p=Store(tmp_path/"data").create(probe(source))
    source.write_bytes(b"changed")
    with pytest.raises(ValueError,match="변경"):
        render(p,Store(tmp_path/"data").directory(p["id"]),lambda *_:None)


@pytest.mark.integration
def test_cut_preview_joins_the_merged_cut_with_sound_and_no_saved_output(tmp_path, sample):
    store = Store(tmp_path)
    p = store.create(probe(sample))
    p["cuts"] = [
        {"id": "a", "start": 2, "end": 4, "enabled": True, "review": False},
        {"id": "b", "start": 3, "end": 4.5, "enabled": True, "review": False},
    ]
    p["captions"] = [{"id": "c", "start": 5, "end": 6, "text": "한국어 컷 연결 검증"}]
    store.save(p)
    def call(action, **values):
        return dispatch({"root": str(tmp_path), "action": action, "id": p["id"], **values})

    saved = store.directory(p["id"]) / "project.json"
    original = saved.read_bytes()
    data = call("cutPreview", revision=0, cutId="b")
    assert (data["cutStart"], data["cutEnd"], data["joinAt"]) == (2, 4.5, 2)
    assert data["before"] == (0, 2) and data["after"] == (4.5, 7.5)
    assert saved.read_bytes() == original and not list(saved.parent.glob("render-*"))
    output = tmp_path / "미리보기.mp4"
    output.write_bytes(base64.b64decode(data["video"]))
    info = probe(output)
    assert info["duration"] == pytest.approx(5, abs=.08)
    assert info["hasAudio"] and info["codec"] == "h264"

    pixel = subprocess.check_output([binary("ffmpeg"), "-v", "error", "-ss", "2.1", "-i", str(output),
                                    "-vf", "crop=2:2:8:8,format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-"])
    assert pixel[2] > 180 and pixel[0] < 30, "The first scene after the jump must come from the blue section"
    audio = subprocess.check_output([binary("ffmpeg"), "-v", "error", "-ss", "2.1", "-i", str(output),
                                    "-t", "0.3", "-f", "s16le", "-"])
    assert any(audio), "The video after the jump must have its original sound"
    with pytest.raises(ValueError, match="다시 선택"):
        call("cutPreview", revision=1, cutId="b")
    p["cuts"].append({"id": "leading", "start": 0, "end": 2, "enabled": True, "review": False})
    store.save(p)
    with pytest.raises(ValueError, match="컷 앞뒤"):
        call("cutPreview", revision=0, cutId="leading")


@pytest.mark.integration
def test_review_candidate_only_shortens_after_explicit_apply(tmp_path,sample):
    from engine.planner import plan
    from engine.project import cut_summary
    original=hashlib.sha256(sample.read_bytes()).hexdigest()
    store=Store(tmp_path)
    p=store.create(probe(sample))
    # Speech timings are fixtures; the rendering and output measurements are real FFmpeg.
    transcript=[{"id":"a","start":.5,"end":1.5,"text":"첫 번째 설명입니다.","confidence":.95,"words":[]},
                {"id":"b","start":6,"end":7.5,"text":"다음 설명입니다.","confidence":.95,"words":[]}]
    p["cuts"],p["warnings"]=plan(p["source"],transcript,[],[],[],[[.5,1.5],[6,7.5]],"basic")
    p.update(transcript=transcript,analyzed=True)
    assert len(p["cuts"])==1 and not p["cuts"][0]["enabled"]
    assert cut_summary(p)["reviewCount"]==1
    store.save(p)
    before=dispatch({"root":str(tmp_path),"action":"render","id":p["id"]})["project"]
    assert abs(before["output"]["duration"]-8)<.15
    cuts=[{**c,"enabled":True} for c in p["cuts"]]
    edited=store.edit(p["id"],{"cuts":cuts})
    expected=cut_summary(edited)["outputDuration"]
    after=dispatch({"root":str(tmp_path),"action":"render","id":p["id"]})["project"]
    assert abs(after["output"]["duration"]-expected)<.15
    assert after["output"]["duration"]<before["output"]["duration"]-3
    report=json.loads(Path(after["output"]["report"]).read_text(encoding="utf-8"))
    assert report["audit"]["cutSummary"]["appliedCount"]==1
    assert after["output"]["revision"]==after["revision"]
    assert hashlib.sha256(sample.read_bytes()).hexdigest()==original


def test_lazy_cuda_failure_restarts_inference_on_cpu(tmp_path,sample,monkeypatch):
    import ctranslate2
    import faster_whisper
    from types import SimpleNamespace
    from engine import analysis
    devices=[]
    class Model:
        def __init__(self,path,device,**kwargs):self.device=device;devices.append(device)
        def transcribe(self,*args,**kwargs):
            def segments():
                if self.device=="cuda":raise RuntimeError("missing CUDA runtime during lazy encode")
                yield SimpleNamespace(start=1,end=2,text=" 테스트 문장입니다.",avg_logprob=-.1,no_speech_prob=.01,words=[])
            return segments(),SimpleNamespace(language="ko")
    monkeypatch.setattr(ctranslate2,"get_cuda_device_count",lambda:1)
    monkeypatch.setattr(faster_whisper,"WhisperModel",Model)
    monkeypatch.setattr(analysis,"ready",lambda *args,**kwargs:True)
    transcript,vad,model=analysis.transcribe(probe(sample),tmp_path,"tiny",tmp_path,lambda *_:None)
    assert devices==["cuda","cpu"] and model["device"]=="cpu" and model["fallback"]
    assert transcript[0]["text"]=="테스트 문장입니다."
    assert not (tmp_path/"analysis.wav").exists()


@pytest.mark.integration
@pytest.mark.parametrize("extension,codec",[(".avi","mpeg4"),(".mov","mpeg4"),(".mkv","libx264")])
def test_supported_containers_get_playable_local_proxy(tmp_path,sample,extension,codec):
    filename=tmp_path/("다른 형식"+extension)
    subprocess.run([binary("ffmpeg"),"-v","error","-y","-i",str(sample),"-t","1","-c:v",codec,"-threads","2","-an",str(filename)],check=True)
    original=hashlib.sha256(filename.read_bytes()).hexdigest()
    p=dispatch({"root":str(tmp_path/"data"),"action":"create","source":str(filename)})
    assert p["source"]["path"]==str(filename) and p["preview"]
    assert probe(p["preview"])["codec"]=="h264"
    assert hashlib.sha256(filename.read_bytes()).hexdigest()==original
