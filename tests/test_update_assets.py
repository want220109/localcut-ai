import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest
import yaml


def verifier():
    path=Path(__file__).resolve().parents[1]/"scripts/verify-update-assets.py"
    spec=importlib.util.spec_from_file_location("update_assets",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.verify


def test_release_manifest_rejects_changed_installer_and_external_path(tmp_path):
    verify=verifier()
    filename="LocalCut-AI-0.2.3-x64-Setup.exe"
    payload=b"MZ"+b"fixture"*100
    (tmp_path/filename).write_bytes(payload)
    (tmp_path/(filename+".blockmap")).write_bytes(b"fixture")
    sha=base64.b64encode(hashlib.sha512(payload).digest()).decode()
    manifest={"version":"0.2.3","path":filename,"sha512":sha,"files":[{"url":filename,"sha512":sha,"size":len(payload)}]}
    (tmp_path/"latest.yml").write_text(yaml.safe_dump(manifest))
    assert verify(tmp_path,"0.2.3")["sha256"]==hashlib.sha256(payload).hexdigest()
    (tmp_path/filename).write_bytes(payload[:-1]+b"!")
    with pytest.raises(ValueError,match="integrity"):
        verify(tmp_path,"0.2.3")
    (tmp_path/filename).write_bytes(payload)
    manifest["files"][0]["url"]="https://unexpected.example/other.exe"
    (tmp_path/"latest.yml").write_text(yaml.safe_dump(manifest))
    with pytest.raises(ValueError,match="payload"):
        verify(tmp_path,"0.2.3")
