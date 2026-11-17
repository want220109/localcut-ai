"""Preserve upstream build sources as release companions; never execute downloads.

Runs only in GitHub Actions. Large sources are split below GitHub's per-asset limit.
The pinned FFmpeg build cache must match the official artifact digest exactly.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

BUILD_SHA="c9fe5114060e507409f7ee07edfd82efaf25d767"
FFMPEG_SHA="f1acb0a2666c78d92688f4c3d2803a132f5590f6"
CACHE_RUN=43712307594
CACHE_ID=14160712668
CACHE_SHA="8ce88272603786d738be990a92e60dcfa9816bd774a81ac7edf61293e0f1c23c"
CHUNK=900*1024*1024


def digest(filename):
    with Path(filename).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def download(url,target,expected=None):
    request=urllib.request.Request(url,headers={"User-Agent":"LocalCut-release-sources/0.2"})
    with urllib.request.urlopen(request,timeout=180) as source,Path(target).open("wb") as destination:
        shutil.copyfileobj(source,destination,1024*1024)
    if expected and digest(target)!=expected:
        Path(target).unlink()
        raise ValueError("Source download checksum mismatch")


def restore_dependency_cache(target):
    """Reuse our permanent, verified release copy after upstream artifacts expire."""
    repo=os.environ["GITHUB_REPOSITORY"]
    releases=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/releases?per_page=100"]))
    for release in releases:
        assets={asset["name"]:asset for asset in release["assets"]}
        if "SOURCE-MANIFEST.json" not in assets:
            continue
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            subprocess.run(["gh","release","download",release["tag_name"],"--pattern","SOURCE-MANIFEST.json","--dir",str(directory)],check=True)
            manifest=json.loads((directory/"SOURCE-MANIFEST.json").read_text(encoding="utf-8"))
            if manifest.get("ffmpegBuildCommit")!=BUILD_SHA or manifest.get("ffmpegCommit")!=FFMPEG_SHA:
                continue
            indexed={item["file"]:item for item in manifest["files"]}
            names=manifest.get("cacheParts",[])
            if not names or any(name not in assets or name not in indexed or Path(name).name!=name or indexed[name].get("origin",{}).get("zipSha256")!=CACHE_SHA for name in names):
                continue
            with Path(target).open("wb") as output:
                for name in names:
                    item=indexed[name]
                    if assets[name].get("digest")!="sha256:"+item["sha256"]:
                        raise ValueError("Stored source asset digest mismatch")
                    subprocess.run(["gh","release","download",release["tag_name"],"--pattern",name,"--dir",str(directory)],check=True)
                    part=directory/name
                    if part.stat().st_size!=item["bytes"] or digest(part)!=item["sha256"]:
                        raise ValueError("Stored source part integrity failure")
                    with part.open("rb") as source:shutil.copyfileobj(source,output,1024*1024)
                    part.unlink()
            if digest(target)!=indexed[names[0]]["reassembledSha256"]:
                raise ValueError("Stored dependency source archive integrity failure")
            print("Reused permanent dependency sources from",release["tag_name"])
            return True
    return False


def main():
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise SystemExit("Source preparation requires an isolated GitHub runner")
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
    notices=Path(sys.argv[2])
    manifest=json.loads((notices/"manifest.json").read_text(encoding="utf-8"))
    records=[]
    def record(filename,origin,**extra):
        filename=Path(filename)
        records.append({"file":filename.name,"bytes":filename.stat().st_size,"sha256":digest(filename),"origin":origin,**extra})
    def parts(filename,origin):
        filename=Path(filename);full_hash=digest(filename);names=[]
        with filename.open("rb") as source:
            count=0
            while data:=source.read(CHUNK):
                count+=1;part=output/(filename.name+f".part{count:03d}");part.write_bytes(data)
                names.append(part.name);record(part,origin,reassembledFile=filename.name,reassembledSha256=full_hash)
        filename.unlink()
        return names
    # Collect the actual source cache belonging to the exact upstream build run.
    cache=output/"ffmpeg-dependency-sources.tar.gz"
    if not restore_dependency_cache(cache):
        archive=output/"upstream-cache.zip"
        with archive.open("wb") as destination:
            result=subprocess.run(["gh","api",f"repos/FFmpeg-Builds/FFmpeg-Builds/actions/artifacts/{CACHE_ID}/zip"],stdout=destination,stderr=subprocess.PIPE)
        if result.returncode:
            # Public artifact mirror is accepted only for the exact official SHA-256.
            download(f"https://nightly.link/FFmpeg-Builds/FFmpeg-Builds/actions/runs/{CACHE_RUN}/download-cache.zip",archive,CACHE_SHA)
        if digest(archive)!=CACHE_SHA:
            raise ValueError("Official upstream source-cache digest mismatch")
        with zipfile.ZipFile(archive) as source:
            entries=[item for item in source.infolist() if Path(item.filename).name=="cache.tar.gz" and not item.is_dir()]
            if len(entries)!=1:
                raise ValueError("Unexpected source cache archive")
            with source.open(entries[0]) as stream,cache.open("wb") as target:
                shutil.copyfileobj(stream,target,1024*1024)
        archive.unlink()
    # Listing only: no downloaded archive path is extracted into the workspace.
    with tarfile.open(cache,"r:gz") as source:
        names=source.getnames()
    if not any("x264" in name for name in names) or not any("downloads" in name for name in names):
        raise ValueError("The pinned cache does not contain dependency sources")
    (output/"ffmpeg-dependency-source-index.txt").write_text("\n".join(names)+"\n",encoding="utf-8")
    cache_parts=parts(cache,{"repository":"FFmpeg-Builds/FFmpeg-Builds","run":CACHE_RUN,"artifact":CACHE_ID,"zipSha256":CACHE_SHA})
    scripts=output/"ffmpeg-build-scripts-and-patches.tar.gz"
    download(f"https://codeload.github.com/FFmpeg-Builds/FFmpeg-Builds/tar.gz/{BUILD_SHA}",scripts)
    record(scripts,{"repository":"FFmpeg-Builds/FFmpeg-Builds","commit":BUILD_SHA})
    # Include the complete FFmpeg history so the separate PyAV/OpenCV wheel FFmpeg
    # revisions remain available too. No shallow/partial clone is used.
    mirror=output/"ffmpeg.git"
    subprocess.run(["git","clone","--mirror","https://github.com/FFmpeg/FFmpeg.git",str(mirror)],check=True)
    subprocess.run(["git","-C",str(mirror),"cat-file","-e",FFMPEG_SHA+"^{commit}"],check=True)
    bundle=output/"ffmpeg-complete-source.bundle"
    subprocess.run(["git","-C",str(mirror),"bundle","create",str(bundle.resolve()),"--all"],check=True)
    shutil.rmtree(mirror)
    bundle_parts=parts(bundle,{"repository":"FFmpeg/FFmpeg","requiredCommit":FFMPEG_SHA,"history":"all refs, full objects"})
    # CPython and the native wrapper/build source distributions, fetched without
    # pip/setup.py or executing any package build hooks.
    python=manifest["pythonVersion"]
    target=output/f"Python-{python}.tar.xz"
    download(f"https://www.python.org/ftp/python/{python}/Python-{python}.tar.xz",target)
    record(target,{"url":f"https://www.python.org/ftp/python/{python}/Python-{python}.tar.xz"})
    for dist in manifest["distributions"]:
        if dist["name"].lower().replace("_","-") not in {"av","opencv-python-headless","pyinstaller"}:
            continue
        url=f"https://pypi.org/pypi/{dist['name']}/{dist['version']}/json"
        with urllib.request.urlopen(url,timeout=60) as response:
            metadata=json.load(response)
        sources=[entry for entry in metadata["urls"] if entry["packagetype"]=="sdist"]
        if len(sources)!=1:
            raise ValueError("Source distribution missing: "+dist["name"])
        entry=sources[0];target=output/Path(entry["filename"]).name
        download(entry["url"],target,entry["digests"]["sha256"])
        record(target,{"pypi":dist["name"],"version":dist["version"],"url":entry["url"]})
    shutil.make_archive(str(output/"runtime-notices"),"zip",notices)
    record(output/"runtime-notices.zip",{"build":"actual Windows distribution metadata and bundled notices"})
    (output/"SOURCE-MANIFEST.json").write_text(json.dumps({"sourceBuild":os.environ.get("LOCALCUT_CANDIDATE_SHA"),"ffmpegBuildCommit":BUILD_SHA,"ffmpegCommit":FFMPEG_SHA,"cacheParts":cache_parts,"ffmpegBundleParts":bundle_parts,"files":records},indent=2)+"\n",encoding="utf-8")
    shutil.copyfile("scripts/reassemble-sources.py",output/"reassemble-sources.py")
    (output/"SOURCES-README.txt").write_text("LocalCut AI corresponding-source companions\n\nRun: python reassemble-sources.py\nThe script verifies every downloaded asset and reassembles the numbered parts.\nFFmpeg: git clone ffmpeg-complete-source.bundle ffmpeg-source\nThen: git -C ffmpeg-source checkout "+FFMPEG_SHA+"\nThe exact FFmpeg-Builds build scripts, patches, configuration and dependency-source\ncache are included. Sources are unmodified; the original GPL/LGPL and other\nlicenses in each source apply. Native wrappers retain their upstream build files.\nNo videos, user data, model weights or credentials are included.\n",encoding="utf-8")
    print(f"Prepared {len(records)} verified source/notice companions")


if __name__=="__main__":
    main()
