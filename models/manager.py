from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from engine.project import atomic_json

CATALOG = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
BASE_FILES = ("config.json", "model.bin", "tokenizer.json")
VOCAB_FILES = ("vocabulary.json", "vocabulary.txt")
# Kept for compatibility with older callers that specifically need the JSON layout.
FILES = BASE_FILES + ("vocabulary.json",)


def required_files(names):
    names = set(names)
    missing = [f for f in BASE_FILES if f not in names]
    vocabulary = next((f for f in VOCAB_FILES if f in names), None)
    if missing or not vocabulary:
        details = ", ".join(missing + ([] if vocabulary else ["vocabulary.json 또는 vocabulary.txt"]))
        raise ValueError("모델 파일이 없습니다: " + details)
    return BASE_FILES + (vocabulary,)


def text_vocabulary(path):
    # Match CTranslate2's Vocabulary::from_text_file exactly: only LF separates
    # tokens; strip CR only when every physical line uses CRLF. Never strip spaces,
    # split other Unicode line separators, sort, or deduplicate the token IDs.
    lines = Path(path).read_bytes().decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if lines and all(line.endswith("\r") for line in lines):
        lines = [line[:-1] for line in lines]
    return lines


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def model_path(root, name):
    if name not in CATALOG:
        raise ValueError("지원하지 않는 모델입니다.")
    return Path(root) / "models" / name


def ready(root, name, verify=False):
    path = model_path(root, name)
    try:
        manifest = json.loads((path / "localcut-manifest.json").read_text(encoding="utf-8"))
        files = required_files(manifest["files"])
        return all((path / f).is_file() and not (path/f).is_symlink() and
                   ((path/f).stat().st_size == manifest["files"][f]["bytes"]) and
                   (not verify or digest(path/f) == manifest["files"][f]["sha256"]) for f in files)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def status(root):
    return [{"id": name, **info, "ready": ready(root, name)} for name, info in CATALOG.items()]


def seal(path, provenance):
    # CTranslate2 is data-only; never import Python code from a model directory.
    config = json.loads((path/"config.json").read_text(encoding="utf-8"))
    json.loads((path/"tokenizer.json").read_text(encoding="utf-8"))
    files = required_files(p.name for p in path.iterdir() if p.is_file() and not p.is_symlink())
    vocabulary = files[-1]
    tokens = json.loads((path/vocabulary).read_text(encoding="utf-8")) if vocabulary.endswith(".json") else text_vocabulary(path/vocabulary)
    if not isinstance(tokens,list) or not tokens or not all(isinstance(token,str) for token in tokens):
        raise ValueError("올바른 모델 어휘 파일이 아닙니다.")
    if not isinstance(config, dict) or (path/"model.bin").stat().st_size < 1024:
        raise ValueError("올바른 faster-whisper 모델 파일이 아닙니다.")
    atomic_json(path / "localcut-manifest.json", {"provenance": provenance, "files": {
        f: {"sha256": digest(path/f), "bytes": (path/f).stat().st_size} for f in files}})


def install(root, name, progress, import_dir=None, *, legacy_json=False, validator=None):
    target = model_path(root, name)
    if ready(root, name, verify=True) and (not legacy_json or (target/"vocabulary.json").is_file()):
        if validator:
            validator(target)
        return {"model": name, "ready": True}
    staging = target.with_name(name + ".partial-" + uuid.uuid4().hex)
    staging.mkdir(parents=True)
    try:
        if import_dir:
            src = Path(import_dir).resolve(strict=True)
            files = required_files(p.name for p in src.iterdir() if p.is_file() and not p.is_symlink())
            for i, f in enumerate(files):
                if not (src/f).is_file() or (src/f).is_symlink():
                    raise ValueError(f"모델 파일 {f}가 없습니다.")
                shutil.copyfile(src/f, staging/f)
                progress(10 + (i+1)*20, f"모델 가져오기: {f}")
            provenance = {"type": "user-import", "directory": str(src)}
        else:
            # This function is reached only through an explicit consent button.
            from huggingface_hub import hf_hub_download, hf_hub_url, get_hf_file_metadata, list_repo_files
            from tqdm.auto import tqdm
            info = CATALOG[name]
            # Converted Whisper repositories publish either vocabulary.txt or JSON.
            # Resolve the actual pinned snapshot before requesting any file.
            progress(0, "고정 버전의 모델 파일 목록 확인 중")
            files = required_files(list_repo_files(info["repo"],revision=info["revision"]))
            for i, f in enumerate(files):
                progress(i*24, f"모델 다운로드: {f}")
                class DownloadProgress(tqdm):
                    def update(self, n=1):
                        result = super().update(n)
                        if self.total:
                            progress(min(96, i*24 + 24*self.n/self.total), f"모델 다운로드: {f} ({self.n/1024/1024:.1f} MB)")
                        return result
                metadata = get_hf_file_metadata(hf_hub_url(info["repo"], f, revision=info["revision"]))
                downloaded = hf_hub_download(info["repo"], f, revision=info["revision"],
                                             cache_dir=str(Path(root)/"download-cache"), tqdm_class=DownloadProgress)
                shutil.copyfile(downloaded, staging/f)
                if len(metadata.etag or "") == 64 and digest(staging/f) != metadata.etag:
                    raise ValueError("모델 다운로드 SHA-256 검증에 실패했습니다.")
            provenance = {"type": "huggingface", "repo": info["repo"], "revision": info["revision"]}
        if legacy_json and files[-1] == "vocabulary.txt":
            tokens = text_vocabulary(staging/"vocabulary.txt")
            provenance["vocabularyConversion"] = {"from": "vocabulary.txt", "sha256": digest(staging/"vocabulary.txt"),
                                                   "to": "vocabulary.json", "method": "CTranslate2 token-order-preserving JSON"}
            atomic_json(staging/"vocabulary.json",tokens)
            (staging/"vocabulary.txt").unlink()
        seal(staging, provenance)
        if validator:
            progress(97, "로컬 CPU에서 실제 모델 불러오기 검증 중")
            validator(staging)
        # Preserve a usable model if Windows blocks the final directory rename.
        backup = target.with_name(name + ".backup-" + uuid.uuid4().hex) if target.exists() else None
        if backup:
            os.replace(target,backup)
        try:
            os.replace(staging, target)
        except BaseException:
            if backup:
                os.replace(backup,target)
            raise
        if backup:
            shutil.rmtree(backup,ignore_errors=True)
        progress(100, "모델 준비 완료 · 이후 오프라인으로 사용 가능")
        return {"model": name, "ready": True}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
