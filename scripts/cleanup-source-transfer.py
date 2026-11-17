"""Delete only our temporary source-transfer artifact after verified draft upload."""
import json
import os
import re
import subprocess
from pathlib import Path

repo=os.environ["GITHUB_REPOSITORY"]
run_id=os.environ["TRANSFER_RUN"]
if not re.fullmatch(r"\d+",run_id):
    raise SystemExit("Invalid transfer run")
def api(endpoint):
    return json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/{endpoint}"]))
run=api(f"actions/runs/{run_id}")
if run["conclusion"]!="success" or run["path"]!=".github/workflows/prepare-update.yml" or run["head_repository"]["full_name"]!=repo:
    raise SystemExit("Only completed, trusted transfer runs may be cleaned")
artifacts=api(f"actions/runs/{run_id}/artifacts")["artifacts"]
transfers=[artifact for artifact in artifacts if artifact["name"]=="release-source-companions"]
releases=api("releases?per_page=100")
validated=False
for release in releases:
    names={item["name"]:item for item in release["assets"]}
    if not {"SOURCE-MANIFEST.json","update-verification.json","latest.yml"}.issubset(names):
        continue
    # gh release download is an authenticated read even for a private draft.
    subprocess.run(["gh","release","download",release["tag_name"],"--pattern","SOURCE-MANIFEST.json","--pattern","update-verification.json","--dir","cleanup-check","--clobber"],check=True)
    with open("cleanup-check/SOURCE-MANIFEST.json",encoding="utf-8") as source:manifest=json.load(source)
    with open("cleanup-check/update-verification.json",encoding="utf-8") as source:evidence=json.load(source)
    if not evidence["upgrade"].get("passed") or evidence["upgrade"].get("harness")!=run["head_sha"] or evidence["build"]!=manifest["sourceBuild"]:
        continue
    if any(item["file"] not in names or names[item["file"]].get("digest")!="sha256:"+item["sha256"] or names[item["file"]]["size"]!=item["bytes"] for item in manifest["files"]):
        raise SystemExit("Permanent source assets incomplete: retaining transfer artifact")
    installer=evidence["installer"]
    if release["target_commitish"]!=evidence["build"] or names.get(installer["installer"],{}).get("digest")!="sha256:"+installer["sha256"] or names[installer["installer"]]["size"]!=installer["bytes"]:
        raise SystemExit("Permanent installer provenance mismatch: retaining source transfer")
    # Draft-owner instructions must not appear in end users' update notes later.
    # Updating notes here is private only; the publication flag is never changed.
    instruction="관리자 검토용 미공개 초안입니다. 관리자가 파일과 검증 결과를 확인하고 Publish release를 눌러야 앱에 공개됩니다."
    expected_tag="v"+installer["version"]
    if release["draft"] and (release["tag_name"]!=expected_tag or instruction in (release.get("body") or "")):
        body=(release.get("body") or "").replace(instruction,"").strip()+"\n"
        patch=Path("cleanup-check/private-notes.json")
        # Keep the semantic tag explicitly: GitHub can otherwise reset an
        # untagged draft's tag_name while its notes are being edited.
        patch.write_text(json.dumps({"body":body,"tag_name":expected_tag,"target_commitish":evidence["build"],"draft":True},ensure_ascii=False),encoding="utf-8")
        subprocess.run(["gh","api","--method","PATCH",f"repos/{repo}/releases/{release['id']}","--input",str(patch)],check=True,stdout=subprocess.DEVNULL)
        release=api(f"releases/{release['id']}")
        if not release["draft"] or release["tag_name"]!=expected_tag or release["target_commitish"]!=evidence["build"]:
            raise SystemExit("Draft version metadata changed unexpectedly; retaining transfer")
    validated=True
    reused=str(manifest.get("materialsArtifactRun",""))
    if reused and reused!=run_id:
        if not re.fullmatch(r"\d+",reused):raise SystemExit("Invalid reused transfer run")
        old=api(f"actions/runs/{reused}")
        if old["path"]!=".github/workflows/prepare-update.yml" or old["head_repository"]["full_name"]!=repo:
            raise SystemExit("Untrusted reused source transfer")
        transfers.extend(artifact for artifact in api(f"actions/runs/{reused}/artifacts")["artifacts"] if artifact["name"]=="release-source-companions")
    break
if not validated:
    raise SystemExit("No verified permanent source copy found; no artifact was removed")
for artifact in transfers:
    subprocess.run(["gh","api","--method","DELETE",f"repos/{repo}/actions/artifacts/{artifact['id']}"],check=True)
    print("Removed completed temporary transfer",artifact["id"])
print(json.dumps({"verified":True,"releaseId":release["id"],"tag":release["tag_name"],"draft":release["draft"],"assetCount":len(names),"build":evidence["build"],"installerSha256":installer["sha256"],"sourceAssetsVerified":True,"removedTemporaryArtifacts":[item["id"] for item in transfers],"publicGitHubUpgradeTested":False}))
