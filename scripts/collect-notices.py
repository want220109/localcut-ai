"""Collect actual installed distribution notices without executing package code or downloading files."""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import re
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FALLBACKS={"ctranslate2":"CTranslate2-LICENSE.txt","tokenizers":"Tokenizers-LICENSE.txt","flatbuffers":"Flatbuffers-LICENSE.txt"}
NOTICE=re.compile(r"(?:^|/)(?:licen[cs]e|copying|copyright|notice|thirdparty)[^/]*(?:$|/)",re.I)


def collect(target):
    target=Path(target)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True,exist_ok=True)
    records=[]
    origins={}
    for dist in sorted(metadata.distributions(),key=lambda d:d.metadata["Name"].lower()):
        name=dist.metadata["Name"]
        safe=re.sub(r"[^A-Za-z0-9_.-]","_",name)+"-"+dist.version
        notices=[]
        for item in dist.files or []:
            relative=Path(str(item).replace("\\","/"))
            if ".." in relative.parts or relative.is_absolute() or not NOTICE.search(relative.as_posix()) or relative.suffix==".pyc":
                continue
            source=Path(dist.locate_file(item))
            if not source.is_file():
                continue
            # Keep paths short enough for Windows/NSIS while preserving exact file bytes.
            label=hashlib.sha256(relative.as_posix().encode()).hexdigest()[:12]+"-"+relative.name[:80]
            destination=target/"python"/safe/label
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,destination)
            notices.append(destination.relative_to(target).as_posix())
            origins[destination.relative_to(target).as_posix()]=relative.as_posix()
        normalized=name.lower().replace("_","-")
        if not notices and normalized in FALLBACKS:
            destination=target/"python"/safe/"LICENSE.txt"
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/"assets/licenses"/FALLBACKS[normalized],destination)
            notices.append(destination.relative_to(target).as_posix())
        records.append({"name":name,"version":dist.version,"license":dist.metadata.get("License-Expression") or dist.metadata.get("License") or "see notices",
                        "notices":notices})
    python_license=next((p for p in [Path(sys.base_prefix)/"LICENSE.txt",Path(sys.base_prefix)/"LICENSE"] if p.is_file()),None)
    if python_license is None:
        if sys.platform=="win32":
            raise RuntimeError("The Windows Python distribution's LICENSE.txt is missing")
        python_license=ROOT/"assets/licenses/Python-3.12-LICENSE.txt"
    shutil.copyfile(python_license,target/"Python-LICENSE.txt")
    shutil.copyfile(ROOT/"LICENSE",target/"LocalCut-LICENSE.txt")
    shutil.copyfile(ROOT/"docs/THIRD_PARTY.md",target/"THIRD_PARTY.md")
    hashes={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob("*") if p.is_file() and p.name!="manifest.json"}
    manifest={"pythonVersion":sys.version.split()[0],"pythonLicenseOrigin":str(python_license.name),"distributions":records,"noticeOrigins":origins,"files":hashes}
    (target/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest


if __name__=="__main__":
    result=collect(ROOT/"vendor/notices")
    print(f"Collected {len(result['files'])} notices for {len(result['distributions'])} build/runtime distributions")
