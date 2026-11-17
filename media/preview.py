from pathlib import Path

from media.tools import binary, run


def compatible_preview(source,directory,progress):
    """Create a local playback proxy for codecs/containers Chromium cannot play."""
    if Path(source["path"]).suffix.lower()==".mp4" and source["codec"]=="h264" and source.get("audioCodec") in {None,"aac","mp3"}:
        return None
    target=Path(directory)/"source-preview.mp4"
    partial=target.with_name("source-preview.partial.mp4")
    progress(5,"호환 미리보기 생성 중 · 원본 영상은 보존합니다")
    try:
        run([binary("ffmpeg"),"-nostdin","-v","error","-y","-i",source["path"],"-map","0:v:0","-map","0:a:0?",
             "-vf","scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30",
             "-c:v","libx264","-preset","veryfast","-crf","25","-threads","2","-pix_fmt","yuv420p",
             "-c:a","aac","-b:a","128k","-movflags","+faststart",str(partial)])
        partial.replace(target)
        progress(100,"호환 미리보기 준비 완료")
        return str(target)
    finally:
        partial.unlink(missing_ok=True)
