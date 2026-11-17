"""Draft retry must verify existing assets without publishing or overwriting them."""
import base64
import hashlib
import json
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("changed",[False,True])
def test_draft_retry_resolves_release_id_and_preserves_existing_assets(tmp_path,monkeypatch,changed):
    script=Path(__file__).resolve().parents[1]/"scripts/stage-update-draft.py"
    monkeypatch.chdir(tmp_path)
    sha="a"*40
    for key,value in {"GITHUB_REPOSITORY":"example/localcut","LOCALCUT_CANDIDATE_SHA":sha,"LOCALCUT_CANDIDATE_VERSION":"0.2.3","LOCALCUT_CANDIDATE_RUN":"123","GITHUB_STEP_SUMMARY":str(tmp_path/"summary.md")}.items():
        monkeypatch.setenv(key,value)
    directory=tmp_path/"candidate/release";directory.mkdir(parents=True)
    name="LocalCut-AI-0.2.3-x64-Setup.exe"
    binary=b"MZ release verification fixture"
    digest=base64.b64encode(hashlib.sha512(binary).digest()).decode()
    (directory/name).write_bytes(binary)
    (directory/(name+".blockmap")).write_bytes(b"blockmap")
    (directory/"latest.yml").write_text(yaml.safe_dump({"version":"0.2.3","path":name,"sha512":digest,"files":[{"url":name,"sha512":digest,"size":len(binary)}]}))
    upgrade={"passed":True,"build":sha,"to":"0.2.3"}
    (tmp_path/"upgrade-results").mkdir()
    (tmp_path/"upgrade-results/result.json").write_text(json.dumps(upgrade))
    sources=tmp_path/"source-companions";sources.mkdir()
    (sources/"runtime-notices.zip").write_bytes(b"existing verified notice fixture")
    notice_hash=hashlib.sha256((sources/"runtime-notices.zip").read_bytes()).hexdigest()
    (sources/"SOURCE-MANIFEST.json").write_text(json.dumps({"sourceBuild":sha,"files":[{"file":"runtime-notices.zip","bytes":(sources/"runtime-notices.zip").stat().st_size,"sha256":notice_hash}]}))
    payload={"version":"0.2.3","installer":name,"bytes":len(binary),"sha256":hashlib.sha256(binary).hexdigest(),"sha512":digest}
    (tmp_path/"update-verification.json").write_text(json.dumps({"installer":payload,"upgrade":upgrade,"build":sha,"run":"123"},indent=2)+"\n")
    assets=[]
    for file in list(directory.iterdir())+list(sources.iterdir())+[tmp_path/"update-verification.json"]:
        assets.append({"name":file.name,"size":file.stat().st_size,"digest":"sha256:"+hashlib.sha256(file.read_bytes()).hexdigest()})
    if changed:assets[0]["digest"]="sha256:"+"0"*64
    release={"id":7,"tag_name":"v0.2.3","draft":True,"prerelease":False,"target_commitish":sha,"html_url":"https://github.com/example/localcut/releases/tag/untagged-fixture","assets":assets}
    requests=[]
    def read(args,**_kwargs):
        endpoint=args[2];requests.append(endpoint)
        if endpoint=="repos/example/localcut/releases":return json.dumps([[release]]).encode()
        if endpoint=="repos/example/localcut/releases/7":return json.dumps(release).encode()
        raise AssertionError("Unexpected API endpoint: "+endpoint)
    def no_write(*_args,**_kwargs):
        raise AssertionError("Verified draft retry must not publish, upload or overwrite an asset")
    monkeypatch.setattr(subprocess,"check_output",read)
    monkeypatch.setattr(subprocess,"run",no_write)
    if changed:
        with pytest.raises(SystemExit,match="differs"):
            runpy.run_path(str(script),run_name="__main__")
    else:
        runpy.run_path(str(script),run_name="__main__")
        assert "repos/example/localcut/releases/7" in requests
        assert "unpublished" in (tmp_path/"summary.md").read_text().lower()
    assert not any("/tags/" in request for request in requests)
