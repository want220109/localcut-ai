"""Delete only our temporary source-transfer artifact after verified draft upload."""
import json
import os
import re
import subprocess

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
if not transfers:
    print("No temporary source transfer remains")
    raise SystemExit(0)
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
    validated=True
    break
if not validated:
    raise SystemExit("No verified permanent source copy found; no artifact was removed")
for artifact in transfers:
    subprocess.run(["gh","api","--method","DELETE",f"repos/{repo}/actions/artifacts/{artifact['id']}"],check=True)
    print("Removed completed temporary transfer",artifact["id"])
