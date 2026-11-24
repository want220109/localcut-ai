"""Shared platform subtitle presets, safe layout and bundled font selection."""
from __future__ import annotations

import copy
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

CATALOG=json.loads(Path(__file__).with_name("presets.json").read_text(encoding="utf-8"))
DEFAULTS=CATALOG["defaults"]
AUTOMATIC_SIZES=CATALOG["automaticSizes"]
FONTS=CATALOG["fonts"]
PRESETS={p["id"]:p for p in CATALOG["presets"]}


def with_defaults(settings):
    return {**copy.deepcopy(DEFAULTS),**settings}


def preset_settings(identifier):
    if identifier not in PRESETS:
        raise ValueError("알 수 없는 자막 프리셋입니다.")
    return {**copy.deepcopy(PRESETS[identifier]["settings"]),"subtitlePreset":identifier,"captionSizeMode":"manual"}


def validate_style(settings):
    s=with_defaults(settings)
    if s["subtitlePreset"] not in {"legacy","custom",*PRESETS} or s["fontFamily"] not in FONTS:
        raise ValueError("지원하지 않는 자막 프리셋 또는 글꼴입니다.")
    if s["captionScale"] not in {"height","short-edge"}:
        raise ValueError("자막 크기 기준이 잘못되었습니다.")
    if s["captionSizeMode"] not in {"auto","manual"}:
        raise ValueError("지원하지 않는 자막 크기 설정입니다.")
    for key in ("fontBold","captionWrap"):
        if type(s[key]) is not bool:raise ValueError("자막 옵션이 잘못되었습니다.")
    for key,maximum in (("captionMarginVertical",40),("captionMarginLeft",30),("captionMarginRight",30),("captionShadow",6)):
        value=s[key]
        if key in {"captionMarginLeft","captionMarginRight"} and value is None:continue
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=maximum:
            raise ValueError("자막 여백 또는 그림자가 허용 범위를 벗어났습니다.")
    if not isinstance(s["captionMaxChars"],int) or isinstance(s["captionMaxChars"],bool) or s["captionMaxChars"] not in {0,*range(8,81)}:
        raise ValueError("자막 문장 길이가 잘못되었습니다.")
    if not isinstance(s["highlightWords"],str) or len(s["highlightWords"])>500:
        raise ValueError("강조 단어는 500자 이내로 입력해 주세요.")
    if not isinstance(s["highlightColor"],str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}",s["highlightColor"]):
        raise ValueError("강조 색상이 잘못되었습니다.")
    return s


def font_directory():
    if getattr(sys,"frozen",False):return Path(sys._MEIPASS)/"fonts"
    return Path(__file__).resolve().parents[1]/"assets"/"fonts"


def selected_font(settings,fallback="Malgun Gothic"):
    spec=FONTS[with_defaults(settings)["fontFamily"]]
    if not spec["file"]:return fallback,None
    filename=spec.get("boldFile") if with_defaults(settings)["fontBold"] and spec.get("boldFile") else spec["file"]
    path=font_directory()/filename
    if not path.is_file():raise RuntimeError("자막 글꼴이 누락되었습니다. 새 버전으로 업데이트해 주세요: "+spec["label"])
    return spec["family"],path


def layout(settings,width,height):
    s=with_defaults(settings)
    basis=min(width,height) if s["captionScale"]=="short-edge" else height
    unit=basis/1080
    left=30 if s["captionMarginLeft"] is None else round(width*s["captionMarginLeft"]/100)
    right=30 if s["captionMarginRight"] is None else round(width*s["captionMarginRight"]/100)
    return {"fontSize":max(12,round(s["fontSize"]*unit)),"outline":s["outline"]*unit,
            "shadow":s["captionShadow"]*unit,"marginLeft":left,"marginRight":right,
            "marginVertical":round(height*s["captionMarginVertical"]/100),"availableWidth":max(1,width-left-right)}


def units(text):
    # Conservative visual width estimate. libass does the final glyph placement.
    return sum(0 if unicodedata.combining(c) else .32 if c.isspace() else 1 if unicodedata.east_asian_width(c) in {"F","W"} else .6 for c in text)


def wrap_text(text,capacity):
    paragraphs=text.split("\n")
    lines=[]
    for paragraph in paragraphs:
        line=""
        for token in re.findall(r"\S+\s*",paragraph):
            if line and units(line+token)>capacity:
                lines.append(line.rstrip());line=""
            for char in token:
                if line and units(line+char)>capacity:
                    lines.append(line.rstrip());line=""
                line+=char
        if line.strip():lines.append(line.rstrip())
    return lines or [""]


def caption_lines(text,geometry):
    size=geometry["fontSize"]
    minimum=min(size,max(10,round(size*.55)))
    # Fit existing/manual captions without changing their words or timestamps.
    while size>=minimum:
        lines=wrap_text(text,geometry["availableWidth"]/(size*1.07))
        if len(lines)<=2:return lines,size
        size-=1
    raise ValueError("두 줄에 들어가지 않는 긴 자막이 있습니다. 자막 내용을 나누거나 글자 크기를 줄여 주세요.")


def bgr(color):
    value=color.lstrip("#")
    return value[4:6]+value[2:4]+value[0:2]


def ass_text(text,settings):
    def escape(value):
        return "".join(c for c in value.replace("\\","＼").replace("{","｛").replace("}","｝") if ord(c)>=32)
    words=sorted({w.strip() for w in settings["highlightWords"].split(",") if w.strip()},key=len,reverse=True)
    if not words:return escape(text)
    pattern=re.compile("("+"|".join(re.escape(w) for w in words)+")")
    parts=pattern.split(text)
    return "".join(("{\\c&H"+bgr(settings["highlightColor"])+"&}"+escape(p)+"{\\c&H"+bgr(settings["color"])+"&}") if i%2 else escape(p) for i,p in enumerate(parts))
