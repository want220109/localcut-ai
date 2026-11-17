from __future__ import annotations

import re

from subtitles.styles import with_defaults, layout, caption_lines, ass_text, bgr, selected_font


def normalize(text):
    # Only whitespace/punctuation formatting. No invented words or speculative spelling changes.
    return re.sub(r"\s+([,.!?，。！？])", r"\1", re.sub(r"\s+", " ", text)).strip()


def generate(transcript, style="basic", settings=None):
    limit = (settings or {}).get("captionMaxChars") or (16 if style == "shorts" else 30)
    result = []
    for s in transcript:
        words = [w for w in s.get("words",[]) if w["end"]>w["start"]]
        if not words:
            result.append({"id":f"c{len(result)}", "start":s["start"], "end":s["end"], "text":normalize(s["text"]), "words":[]})
            continue
        chunk = []
        for w in words:
            if chunk and (len(normalize("".join(c["text"] for c in chunk)+w["text"]))>limit or
                          w["end"]-chunk[0]["start"]>4 or w["start"]-chunk[-1]["end"]>.65):
                result.append({"id":f"c{len(result)}", "start":chunk[0]["start"], "end":chunk[-1]["end"],
                               "text":normalize("".join(c["text"] for c in chunk)), "words":chunk})
                chunk = []
            chunk.append(w)
        if chunk:
            result.append({"id":f"c{len(result)}", "start":chunk[0]["start"], "end":chunk[-1]["end"],
                           "text":normalize("".join(c["text"] for c in chunk)), "words":chunk})
    return result


def remap(captions, intervals):
    result, offset = [], 0.0
    for a,b in intervals:
        for c in captions:
            start, end = max(a,c["start"]), min(b,c["end"])
            if end-start < .04:
                continue
            words = [w for w in c.get("words",[]) if a <= (w["start"]+w["end"])/2 < b]
            if words and not c.get("textEdited"):
                text = normalize("".join(w["text"] for w in words))
            elif c.get("words") and not c.get("textEdited"):
                continue
            else:
                # Edited captions occur once in the interval with largest overlap.
                winner = max(intervals,key=lambda r:max(0,min(r[1],c["end"])-max(r[0],c["start"])))
                if winner != [a,b] and tuple(winner) != (a,b):
                    continue
                text = "\n".join(normalize(row) for row in c["text"].replace("\r\n","\n").replace("\r","\n").split("\n") if row.strip())
            if text:
                result.append({"start": offset+start-a, "end": offset+end-a, "text":text})
        offset += b-a
    result.sort(key=lambda c:c["start"])
    for left,right in zip(result,result[1:]):
        left["end"] = min(left["end"],right["start"])
    return [c for c in result if c["end"]-c["start"]>=.025]


def stamp(seconds, ass=False):
    scale = 100 if ass else 1000
    ticks = max(0, round(seconds*scale))
    sec, fraction = divmod(ticks,scale)
    minutes, sec = divmod(sec,60)
    hours, minutes = divmod(minutes,60)
    return f"{hours}:{minutes:02}:{sec:02}.{fraction:02}" if ass else f"{hours:02}:{minutes:02}:{sec:02},{fraction:03}"


def srt(captions):
    # Strip SRT formatting delimiters so user edits remain plain text.
    return "\n\n".join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text'].replace('-->', '→')}" for i,c in enumerate(captions))+"\n"


def ass(captions, settings, width, height, font="Malgun Gothic"):
    settings=with_defaults(settings)
    geometry=layout(settings,width,height)
    font,_=selected_font(settings,font)
    color = bgr(settings["color"])
    alignment = {"bottom":2,"middle":5,"top":8}[settings["position"]]
    size = geometry["fontSize"]
    outline = geometry["outline"]
    border = 3 if settings["background"] else 1
    margin = geometry["marginVertical"]
    bold=-1 if settings["fontBold"] else 0
    left,right=geometry["marginLeft"],geometry["marginRight"]
    shadow=geometry["shadow"]
    outline_color="&H80000000" if settings["background"] or settings["subtitlePreset"]=="legacy" else "&H00000000"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00{color},&H00{color},{outline_color},&H80000000,{bold},0,0,0,100,100,0,0,{border},{outline},{shadow},{alignment},{left},{right},{margin},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[]
    for c in captions:
        if settings["captionWrap"]:
            rows,actual_size=caption_lines(c["text"],geometry)
        else:
            rows,actual_size=c["text"].split("\n"),size
        text="\\N".join(ass_text(row,settings) for row in rows)
        if actual_size!=size:text="{\\fs"+str(actual_size)+"}"+text
        lines.append(f"Dialogue: 0,{stamp(c['start'],True)},{stamp(c['end'],True)},Default,,0,0,0,,{text}")
    return header+"\n".join(lines)+"\n"
