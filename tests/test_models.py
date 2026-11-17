import json

import pytest

from models.manager import FILES, BASE_FILES, digest, install, model_path, ready, status, text_vocabulary


def fixture_model(path, vocabulary="json"):
    path.mkdir()
    (path/"config.json").write_text('{"model_type":"whisper"}')
    (path/"tokenizer.json").write_text('{}')
    if vocabulary == "json":
        (path/"vocabulary.json").write_text('["a", "b"]')
    else:
        (path/"vocabulary.txt").write_bytes("a\n한국어\n".encode("utf-8"))
    (path/"model.bin").write_bytes(b"fixture-data-not-a-real-model"*100)


def test_offline_import_is_atomic_and_detects_corruption(tmp_path):
    source=tmp_path/"offline";fixture_model(source)
    data=tmp_path/"data";events=[]
    install(data,"tiny",lambda n,m:events.append(n),source)
    assert ready(data,"tiny",verify=True) and events[-1]==100
    binary=model_path(data,"tiny")/"model.bin"
    contents=binary.read_bytes();binary.write_bytes(b"X"+contents[1:])
    assert not ready(data,"tiny",verify=True)


def test_failed_import_does_not_leave_ready_partial_model(tmp_path):
    source=tmp_path/"bad";source.mkdir()
    with pytest.raises(ValueError,match="모델 파일"):
        install(tmp_path/"data","small",lambda *_:None,source)
    assert not ready(tmp_path/"data","small")
    assert not list((tmp_path/"data"/"models").glob("*.partial-*"))
    with pytest.raises(ValueError):model_path(tmp_path,"../escape")


@pytest.mark.parametrize("vocabulary",["json","txt"])
def test_both_vocabulary_formats_import_and_verify(tmp_path,vocabulary):
    source=tmp_path/"offline";fixture_model(source,vocabulary)
    install(tmp_path/"data","small",lambda *_:None,source)
    assert ready(tmp_path/"data","small",verify=True)
    directory=model_path(tmp_path/"data","small")
    manifest=json.loads((directory/"localcut-manifest.json").read_text())
    assert f"vocabulary.{vocabulary}" in manifest["files"]


def test_text_vocabulary_conversion_preserves_native_token_ids(tmp_path):
    source=tmp_path/"offline";fixture_model(source,"txt")
    # Unicode line separators, spaces, empty tokens and literal CR inside a token
    # must not be changed by a convenient but incompatible splitlines()/strip().
    tokens=[" ","한국어","x\u2028y","","carriage\r","last"]
    (source/"vocabulary.txt").write_bytes(("\n".join(tokens)+"\n").encode("utf-8"))
    install(tmp_path/"data","small",lambda *_:None,source,legacy_json=True)
    directory=model_path(tmp_path/"data","small")
    assert json.loads((directory/"vocabulary.json").read_text(encoding="utf-8"))==tokens
    assert not (directory/"vocabulary.txt").exists()
    assert ready(tmp_path/"data","small",verify=True)
    # The original 0.1.0 runtime requires precisely these four files and hashes.
    manifest=json.loads((directory/"localcut-manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"])==set(FILES)
    assert manifest["provenance"]["vocabularyConversion"]["from"]=="vocabulary.txt"
    (source/"vocabulary.txt").write_bytes(b"a\r\nb\r\n")
    assert text_vocabulary(source/"vocabulary.txt")==["a","b"]


def test_failed_native_validation_preserves_previous_model(tmp_path):
    data=tmp_path/"data";source=tmp_path/"offline";fixture_model(source)
    target=model_path(data,"small")
    target.parent.mkdir(parents=True)
    # A complete TXT model needs conversion for the installed JSON-only app.
    fixture_model(target,"txt")
    from models.manager import seal
    seal(target,{"type":"test"})
    old_manifest=(target/"localcut-manifest.json").read_bytes()
    def reject(path):raise RuntimeError("native load failed")
    with pytest.raises(RuntimeError,match="native load failed"):
        install(data,"small",lambda *_:None,source,legacy_json=True,validator=reject)
    assert (target/"localcut-manifest.json").read_bytes()==old_manifest
    assert ready(data,"small",verify=True)
    assert not list(target.parent.glob("*.partial-*"))


@pytest.mark.parametrize("legacy_json",[False,True])
def test_download_selects_published_txt_and_reuses_cache(tmp_path,monkeypatch,legacy_json):
    import huggingface_hub as hub
    from types import SimpleNamespace
    repo=tmp_path/"published";fixture_model(repo,"txt")
    requested=[]
    monkeypatch.setattr(hub,"list_repo_files",lambda *args,**kwargs:[*BASE_FILES,"vocabulary.txt","README.md"])
    monkeypatch.setattr(hub,"hf_hub_url",lambda repo,filename,**kwargs:filename)
    monkeypatch.setattr(hub,"get_hf_file_metadata",lambda filename:SimpleNamespace(etag=digest(repo/filename)))
    def download(repository,filename,**kwargs):
        requested.append(filename)
        assert kwargs["cache_dir"]==str(tmp_path/"data"/"download-cache")
        return str(repo/filename)
    monkeypatch.setattr(hub,"hf_hub_download",download)
    checked=[]
    install(tmp_path/"data","small",lambda *_:None,legacy_json=legacy_json,validator=lambda p:checked.append(p.is_dir()))
    assert requested==[*BASE_FILES,"vocabulary.txt"]
    assert "vocabulary.json" not in requested and checked==[True]
    assert ready(tmp_path/"data","small",verify=True)


def load_repair_helper():
    import importlib.util
    from pathlib import Path
    script=Path(__file__).resolve().parents[1]/"scripts"/"repair-speech-model.py"
    spec=importlib.util.spec_from_file_location("localcut_model_repair_test",script)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_helper_reports_native_load_failure_without_success(tmp_path,monkeypatch):
    helper=load_repair_helper()
    data=tmp_path/"userdata";data.mkdir()
    project=tmp_path/"project";project.mkdir()
    monkeypatch.setattr(helper,"ROOT",project)
    monkeypatch.setattr(helper,"check_app_closed",lambda:None)
    def fail(*args,**kwargs):raise RuntimeError("actual model load failed")
    monkeypatch.setattr(helper,"install",fail)
    assert helper.main(["--data-root",str(data)])==1
    result=json.loads((project/"model-repair-results"/"result.json").read_text(encoding="utf-8"))
    assert result["status"]=="FAILED" and not result["nativeCpuLoadVerified"]
    assert "actual model load failed" in result["error"]


def test_repair_helper_checks_actual_model_before_marking_success(tmp_path,monkeypatch):
    helper=load_repair_helper()
    data=tmp_path/"userdata";data.mkdir()
    jobs=data/"jobs";jobs.mkdir();(jobs/"keep.txt").write_text("existing user job")
    project=tmp_path/"project";project.mkdir()
    monkeypatch.setattr(helper,"ROOT",project)
    monkeypatch.setattr(helper,"check_app_closed",lambda:None)
    checked=[]
    monkeypatch.setattr(helper,"validate_cpu_model",lambda p:checked.append(str(p)))
    def install_mock(root,name,progress,**kwargs):
        assert kwargs["legacy_json"] is True
        kwargs["validator"](model_path(root,name))
    monkeypatch.setattr(helper,"install",install_mock)
    monkeypatch.setattr(helper,"ready",lambda *args,**kwargs:True)
    assert helper.main(["--data-root",str(data)])==0
    result=json.loads((project/"model-repair-results"/"result.json").read_text(encoding="utf-8"))
    assert result["status"]=="MODEL_REPAIRED_AND_CPU_LOADED" and len(checked)==1
    assert result["speechRecognitionTest"]=="NOT_RUN"
    assert (jobs/"keep.txt").read_text()=="existing user job"


def test_windows_style_activation_failure_restores_previous_model(tmp_path,monkeypatch):
    import os
    from pathlib import Path
    from models.manager import seal
    data=tmp_path/"data";source=tmp_path/"offline";fixture_model(source)
    target=model_path(data,"small");target.parent.mkdir(parents=True)
    fixture_model(target,"txt");seal(target,{"type":"test"})
    old_manifest=(target/"localcut-manifest.json").read_bytes()
    replace=os.replace
    def deny_activation(src,dst):
        if Path(src).name.startswith("small.partial-") and Path(dst)==target:
            raise PermissionError("simulated Windows sharing violation")
        return replace(src,dst)
    monkeypatch.setattr(os,"replace",deny_activation)
    with pytest.raises(PermissionError,match="sharing violation"):
        install(data,"small",lambda *_:None,source,legacy_json=True)
    assert (target/"localcut-manifest.json").read_bytes()==old_manifest
    assert ready(data,"small",verify=True)
    assert not list(target.parent.glob("*.partial-*"))
    assert not list(target.parent.glob("*.backup-*"))


@pytest.mark.parametrize("name",["LocalCut AI","localcut-ai"])
def test_repair_finds_electron_data_folder_without_losing_cache(tmp_path,name):
    helper=load_repair_helper()
    for candidate in ("LocalCut AI","localcut-ai"):
        (tmp_path/candidate/"workspace").mkdir(parents=True)
    expected=tmp_path/name/"workspace";(expected/"download-cache").mkdir()
    assert helper.find_data_root(tmp_path)==expected


def test_repair_refuses_ambiguous_app_data_folders(tmp_path):
    helper=load_repair_helper()
    for name in ("LocalCut AI","localcut-ai"):
        (tmp_path/name/"workspace").mkdir(parents=True)
    with pytest.raises(RuntimeError,match="여러 개"):
        helper.find_data_root(tmp_path)
