"""Download a pinned Windows FFmpeg build; verify before extracting executable files."""
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TAG="autobuild-2026-11-15-12-40"
ASSET="ffmpeg-n8.1.3-35-gf1acb0a266-win64-gpl-8.1.zip"
SHA256="ce121fcc8fe8097d6ab65c97ce34dc38b9e17006c31af26088ac6c91634dff28"
URL=f"https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/{TAG}/{ASSET}"


def main():
    cache=ROOT/"vendor";cache.mkdir(exist_ok=True)
    archive=cache/ASSET
    if not archive.exists():
        request=urllib.request.Request(URL,headers={"User-Agent":"LocalCut-build/0.1"})
        with urllib.request.urlopen(request,timeout=120) as src, archive.with_suffix(".partial").open("wb") as out:
            shutil.copyfileobj(src,out)
        archive.with_suffix(".partial").replace(archive)
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    if checksum!=SHA256:
        archive.unlink()
        raise SystemExit("FFmpeg SHA-256 mismatch; refusing to extract or execute.")
    target=cache/"media";target.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in ("ffmpeg.exe","ffprobe.exe"):
            member=next(n for n in z.namelist() if n.endswith("/bin/"+name))
            with z.open(member) as src,(target/name).open("wb") as out:
                shutil.copyfileobj(src,out)
        # Include upstream license files without extracting arbitrary archive paths.
        for n in z.namelist():
            if "license" in n.lower() and not n.endswith("/"):
                dest=target/("upstream-"+Path(n).name)
                dest.write_bytes(z.read(n))
    (target/"provenance.json").write_text(json.dumps({"url":URL,"sha256":SHA256,"tag":TAG,
       "source":"https://github.com/FFmpeg-Builds/FFmpeg-Builds", "ffmpegCommit":"f1acb0a266"},indent=2),encoding="utf-8")
    print(f"Verified FFmpeg/FFprobe in {target}")


if __name__=="__main__":main()
