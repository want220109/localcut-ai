import copy
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

from engine.project import Store, atomic_json
from media.render import render
from media.caption_frame import caption_frame
from media.tools import binary, probe
from subtitles.captions import ass, generate, remap, srt
from subtitles.styles import DEFAULTS, PRESETS, caption_lines, font_directory, layout, preset_settings, selected_font, validate_style


def source():
    return {"path":"original.mp4","duration":10,"width":1920,"height":1080,"fps":30,"aspect":"16:9","hasAudio":False,"bytes":1,"mtimeNs":1}


def test_old_project_keeps_its_style_and_edits(tmp_path):
    store=Store(tmp_path);p=store.create(source())
    p["settings"]["fontSize"]=56
    p["captions"]=[{"id":"manual","start":1,"end":3,"text":"직접 수정한 자막", "textEdited":True}]
    p["cuts"]=[{"id":"cut","start":5,"end":6,"enabled":True,"review":False}]
    for key in DEFAULTS:p["settings"].pop(key,None)
    atomic_json(store.directory(p["id"])/"project.json",p)
    loaded=store.load(p["id"])
    assert loaded["settings"]["subtitlePreset"]=="legacy" and loaded["settings"]["fontSize"]==56
    assert loaded["settings"]["captionSizeMode"]=="manual" and loaded["settings"]["captionScale"]=="height"
    assert loaded["captions"]==p["captions"] and loaded["cuts"]==p["cuts"]
    before=copy.deepcopy(loaded)
    edited=store.edit(p["id"],{"settings":preset_settings("shorts_pop")})
    assert edited["captions"]==before["captions"] and edited["cuts"]==before["cuts"]
    assert edited["source"]==before["source"]
    for key in ("aspect","resolution","quality","zoom"):
        assert edited["settings"][key]==before["settings"][key]


def test_default_size_tracks_output_orientation_until_manually_overridden(tmp_path):
    store=Store(tmp_path)
    project=store.create(source())
    project_id=project["id"]
    assert project["settings"]["fontSize"]==64 and project["settings"]["captionScale"]=="short-edge"
    vertical=store.edit(project_id,{"style":"shorts","settings":{"aspect":"9:16"}})
    assert vertical["settings"]["fontSize"]==80
    store.edit(project_id,{"settings":{"fontSize":72}})
    resized=store.edit(project_id,{"settings":{"aspect":"16:9"}})
    assert resized["settings"]["fontSize"]==72 and resized["settings"]["captionSizeMode"]=="manual"
    automatic=store.edit(project_id,{"settings":{"captionSizeMode":"auto"}})
    assert automatic["settings"]["fontSize"]==64
    portrait=store.create({**source(),"width":1080,"height":1920,"aspect":"9:16"})
    assert portrait["settings"]["fontSize"]==80
    assert preset_settings("youtube_clean")["fontSize"]==64
    assert preset_settings("youtube_box")["fontSize"]==64


def test_portrait_size_uses_short_edge_and_safe_margins(tmp_path):
    settings={**Store(tmp_path).create(source())["settings"],**preset_settings("shorts_pop")}
    large=layout(settings,1080,1920);small=layout(settings,720,1280)
    assert large["fontSize"]==80 and small["fontSize"]==53
    assert large["marginVertical"]==442
    assert large["marginRight"]>large["marginLeft"]
    legacy=layout({**settings,"captionScale":"height"},1080,1920)
    assert legacy["fontSize"]==142


def test_wrapping_preserves_words_and_escapes_ass_commands(tmp_path):
    settings={**Store(tmp_path).create(source())["settings"],**preset_settings("reels_minimal"),"highlightWords":"핵심,추천","highlightColor":"#D6FF62"}
    text="오늘의 핵심은 원본의 이야기를 그대로 보존하는 것입니다."
    geometry=layout(settings,720,1280)
    rows,size=caption_lines(text,geometry)
    assert len(rows)<=2 and ''.join(rows).replace(' ','')==text.replace(' ','')
    cues=[{"start":1,"end":3,"text":text+" {\\pos(0,0)}"}]
    data=ass(cues,settings,720,1280)
    assert "\\pos" not in data and "{\\c&H62FFD6&}" in data
    assert data.count("Dialogue:")==1
    assert '핵심' in srt(cues) and '{\\c' not in srt(cues)


def test_preset_changes_caption_segmentation_without_inventing_words():
    words=[{"start":i*.2,"end":(i+1)*.2,"text":(" " if i else "")+word} for i,word in enumerate(["오늘은","한국어","영상의","자막을","아름답게","만들어","보겠습니다"])]
    transcript=[{"start":0,"end":1.4,"text":"".join(w["text"] for w in words),"words":words}]
    result=generate(transcript,"basic",preset_settings("shorts_pop"))
    assert len(result)>=2
    assert ' '.join(c["text"] for c in result)==transcript[0]["text"]
    assert result[0]["start"]==0 and result[-1]["end"]==pytest.approx(1.4)


def test_edited_line_breaks_survive_timeline_mapping():
    cue={"id":"manual","start":2,"end":4,"text":"첫 번째 줄\n두 번째 줄","textEdited":True}
    mapped=remap([cue],[[1,5]])
    assert mapped[0]["text"]==cue["text"] and mapped[0]["start"]==1
    assert '첫 번째 줄\n두 번째 줄' in srt(mapped)


@pytest.mark.parametrize("changes",[{"fontFamily":"arbitrary,\\path"},{"subtitlePreset":"unknown"},{"highlightColor":"{\\an8}"},{"captionMarginRight":float("nan")},{"fontBold":1},{"captionMaxChars":999}])
def test_invalid_subtitle_options_are_rejected(tmp_path,changes):
    store=Store(tmp_path);p=store.create(source())
    with pytest.raises(ValueError):store.edit(p["id"],{"settings":changes})
    assert store.load(p["id"])["revision"]==0


def test_bundled_fonts_match_reviewed_originals_and_include_licenses():
    directory=font_directory()
    sources=json.loads((directory/"SOURCES.json").read_text())
    assert len(sources)==5
    for info in sources:
        data=(directory/info["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest()==info["sha256"]
        assert hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()==info["gitBlob"]
        if info["file"].endswith('.txt'):assert b'OPEN FONT LICENSE' in data.upper()
    settings={**DEFAULTS,"fontFamily":"nanum","fontBold":False}
    assert selected_font(settings)[1].name=="NanumGothic-Regular.ttf"
    assert selected_font({**settings,"fontBold":True})[1].name=="NanumGothic-Bold.ttf"


@pytest.fixture(scope="module")
def solid_video(tmp_path_factory):
    path=tmp_path_factory.mktemp("자막 글꼴 검증")/"원본.mp4"
    subprocess.run([binary("ffmpeg"),"-v","error","-y","-f","lavfi","-i","color=c=0x181c24:size=640x360:rate=24:duration=1",
                    "-c:v","libx264","-threads","2","-pix_fmt","yuv420p",str(path)],check=True)
    return path


@pytest.mark.integration
def test_caption_frame_shows_unsaved_text_at_the_larger_size_without_changing_project(tmp_path,solid_video):
    import cv2

    store=Store(tmp_path)
    project=store.create(probe(solid_video))
    project_id=project["id"]
    saved={"id":"caption","start":0.1,"end":0.9,"text":"원본 자막"}
    project=store.edit(project_id,{"captions":[saved],"settings":preset_settings("youtube_clean")})
    draft={**saved,"text":"수정 중인 자막"}

    def pixels(frame):
        data=base64.b64decode(frame["image"].split(",",1)[1])
        return cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR)

    original=caption_frame(project,saved)
    edited=caption_frame(project,draft)
    assert original["sourceTime"]==edited["sourceTime"]==0.5
    assert not np.array_equal(pixels(original),pixels(edited))

    bigger=store.edit(project_id,{"settings":{"fontSize":160}})
    large=pixels(caption_frame(bigger,draft))
    normal=pixels(edited)
    assert large.shape==normal.shape==(360,640,3)
    assert np.count_nonzero(np.all(large>180,axis=2))>np.count_nonzero(np.all(normal>180,axis=2))
    assert store.load(project_id)["captions"]==[saved]
    assert bigger["output"] is None

    updated=store.edit(project_id,{"captions":[{**draft,"textEdited":True}]})
    output=render(updated,store.directory(project_id),lambda *_:None)
    decoded=subprocess.check_output([binary("ffmpeg"),"-v","error","-ss","0.5","-i",output["path"],
                                     "-frames:v","1","-pix_fmt","bgr24","-f","rawvideo","pipe:1"])
    exported=np.frombuffer(decoded,dtype=np.uint8).reshape(large.shape)
    preview_ink=np.all(large>180,axis=2)
    export_ink=np.all(exported>180,axis=2)
    assert np.count_nonzero(preview_ink & export_ink)/np.count_nonzero(preview_ink | export_ink)>.9

    cut={"id":"cut","start":0.3,"end":0.7,"enabled":True,"review":False}
    trimmed=store.edit(project_id,{"cuts":[cut]})
    retained=caption_frame(trimmed,draft)
    assert retained["message"] is None
    assert retained["sourceTime"]<0.3 or retained["sourceTime"]>=0.7
    removed=caption_frame(trimmed,{**draft,"start":0.35,"end":0.65})
    assert "표시되지 않습니다" in removed["message"]


@pytest.mark.integration
@pytest.mark.parametrize("preset_id",list(PRESETS))
def test_every_preset_encodes_real_korean_glyphs_inside_safe_area(tmp_path,solid_video,preset_id):
    store=Store(tmp_path);p=store.create(probe(solid_video))
    original=hashlib.sha256(solid_video.read_bytes()).hexdigest()
    p["settings"].update(preset_settings(preset_id))
    p["settings"].update(resolution="720",aspect=PRESETS[preset_id]["aspect"],highlightWords="핵심")
    p["captions"]=[{"id":"s","start":0,"end":1,"text":"오늘의 핵심을 함께 살펴봐요"}]
    result=render(p,store.directory(p["id"]),lambda *_:None)
    out=probe(result["path"]);w,h=out["width"],out["height"]
    frame=subprocess.check_output([binary("ffmpeg"),"-v","error","-ss","0.5","-i",result["path"],"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-"])
    pixels=np.frombuffer(frame,dtype=np.uint8).reshape(h,w,3)
    ys,xs=np.where(pixels.max(axis=2)>160)
    geometry=layout(p["settings"],w,h)
    assert len(xs)>50
    assert xs.min()>=geometry["marginLeft"]-3 and xs.max()<=w-geometry["marginRight"]+3
    assert ys.max()<=h-geometry["marginVertical"]+3
    rgb=pixels.astype(float)
    assert ((rgb[:,:,1]>rgb[:,:,0]*1.05)&(rgb[:,:,1]>rgb[:,:,2]*1.2)&(rgb[:,:,1]>160)).sum()>5
    log=Path(result["path"]).with_name('ffmpeg.log').read_text(encoding="utf-8")
    assert selected_font(p["settings"])[1].name in log
    assert 'fontselect:' in log
    assert hashlib.sha256(solid_video.read_bytes()).hexdigest()==original
