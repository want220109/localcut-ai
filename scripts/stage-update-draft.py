"""Prepare a private release draft. This script never publishes a release."""
import hashlib
import importlib.util
import json
import os
import subprocess
import zipfile
from pathlib import Path

repo=os.environ["GITHUB_REPOSITORY"]
sha=os.environ["LOCALCUT_CANDIDATE_SHA"]
version=os.environ["LOCALCUT_CANDIDATE_VERSION"]
run_id=os.environ["LOCALCUT_CANDIDATE_RUN"]
tag="v"+version
module_path=Path(__file__).with_name("verify-update-assets.py")
spec=importlib.util.spec_from_file_location("verify_assets",module_path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
payload=module.verify("candidate/release",version)
upgrade=json.loads(Path("upgrade-results/result.json").read_text(encoding="utf-8"))
if not upgrade.get("passed") or upgrade.get("build")!=sha or upgrade.get("to")!=version:
    raise SystemExit("Installed upgrade evidence does not match candidate")
sources=Path("source-companions")
manifest=json.loads((sources/"SOURCE-MANIFEST.json").read_text(encoding="utf-8"))
if manifest["sourceBuild"]!=sha:
    # Source companions contain native third-party sources, no LocalCut binaries.
    # A rebuild may reuse them only when all actual installed notices and versions
    # are byte-identical. Preserve both collection and candidate provenance.
    with zipfile.ZipFile(sources/"runtime-notices.zip") as archive:
        original=json.loads(archive.read("manifest.json"))
    current=json.loads(Path("candidate/vendor/notices/manifest.json").read_text(encoding="utf-8"))
    if original!=current:
        raise SystemExit("Native source materials do not match this runtime")
    manifest["materialsCollectedFor"]=manifest["sourceBuild"]
    manifest["materialsArtifactRun"]=os.environ["LOCALCUT_SOURCE_TRANSFER_RUN"]
    manifest["sourceBuild"]=sha
    (sources/"SOURCE-MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
for item in manifest["files"]:
    file=sources/item["file"]
    if file.parent!=sources or not file.is_file() or file.stat().st_size!=item["bytes"]:
        raise SystemExit("Missing source companion")
    with file.open("rb") as stream:
        if hashlib.file_digest(stream,"sha256").hexdigest()!=item["sha256"]:
            raise SystemExit("Source companion integrity failure")
pages=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/releases","--paginate","--slurp"]))
existing=[release for page in pages for release in page]
previous=next((release for release in existing if release["tag_name"]==tag),None)
if previous and (not previous["draft"] or previous["target_commitish"]!=sha):
    raise SystemExit("A different or published release already exists; it will not be modified")
verification=Path("update-verification.json")
verification.write_text(json.dumps({"installer":payload,"upgrade":upgrade,"build":sha,"run":run_id},indent=2)+"\n",encoding="utf-8")
assets=list(Path("candidate/release").glob("*Setup.exe"))+list(Path("candidate/release").glob("*.blockmap"))+[Path("candidate/release/latest.yml"),verification]+list(sources.iterdir())
assets=[file for file in assets if file.is_file()]
changelog=(Path(__file__).resolve().parents[1]/"CHANGELOG.md").read_text(encoding="utf-8")
sections=changelog.split("\n## ")[1:]
changes=next((section.partition("\n")[2].strip() for section in sections if section.startswith(version+" —")),"")
notes=f"""LocalCut AI {tag}

앱의 모델 · 업데이트 → 업데이트 확인 → 다운로드 → 설치하고 재시작으로 적용합니다. 설치 파일을 별도로 실행할 필요가 없습니다. 기존 작업·모델은 유지됩니다.

{changes}

검증: Windows {upgrade.get('from','이전 버전')} 설치본에서 후보 피드를 통한 실제 다운로드·SHA-512 손상 거부·NSIS 설치·자동 재시작·자막/컷/설정 및 작업 폴더 보존·MP4 출력 통과. 공개 GitHub 피드 업그레이드는 게시 후 별도 확인 대상입니다. 실제 사용자 PC·한국어 ASR·CUDA 검증과는 구분합니다.

빌드: https://github.com/{repo}/actions/runs/{run_id}
소스: {sha}
설치본 SHA-256: {payload['sha256']}

FFmpeg와 포함 네이티브 구성의 대응 소스·빌드 스크립트·패치·라이선스는 이 릴리스의 source bundle, dependency source parts, source distributions, runtime-notices.zip 및 SOURCE-MANIFEST.json을 참고하세요. 분할 자료는 reassemble-sources.py로 검증·결합합니다. 소스 자료는 앱 업데이트 시 다운로드하지 않습니다.

"""
Path("draft-notes.md").write_text(notes,encoding="utf-8")
if previous is None:
    subprocess.run(["gh","release","create",tag,"--draft","--target",sha,"--title",f"LocalCut AI {version}","--notes-file","draft-notes.md"],check=True)
remote={asset["name"]:asset for asset in (previous or {}).get("assets",[])}
for asset in assets:
    if asset.name in remote:
        with asset.open("rb") as stream:
            expected="sha256:"+hashlib.file_digest(stream,"sha256").hexdigest()
        if remote[asset.name].get("digest")!=expected or remote[asset.name]["size"]!=asset.stat().st_size:
            raise SystemExit("Existing draft asset differs; no asset was overwritten")
        continue
    subprocess.run(["gh","release","upload",tag,str(asset)],check=True)
# GitHub's release-by-tag endpoint can return 404 for a draft without a tag ref.
# Resolve the authenticated draft by immutable release ID instead.
pages=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/releases","--paginate","--slurp"]))
updated=next((item for page in pages for item in page if item["tag_name"]==tag),None)
if updated is None:
    raise SystemExit("Prepared release draft is missing")
release=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/releases/{updated['id']}"]))
if not release["draft"] or release["prerelease"] or release["tag_name"]!=tag or release["target_commitish"]!=sha:
    raise SystemExit("Release must remain an unpublished stable draft")
remote={asset["name"]:asset for asset in release["assets"]}
for asset in assets:
    with asset.open("rb") as stream:
        expected="sha256:"+hashlib.file_digest(stream,"sha256").hexdigest()
    if asset.name not in remote or remote[asset.name]["size"]!=asset.stat().st_size or remote[asset.name].get("digest")!=expected:
        raise SystemExit("Draft asset upload incomplete")
print("Prepared unpublished release draft:",release["html_url"])
with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as output:
    output.write(f"Unpublished draft: {release['html_url']}\n\nAll installer, manifest, blockmap and source companions uploaded. An owner must review and publish this draft. No public release was created.\n")
