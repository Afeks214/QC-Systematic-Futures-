from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts import verify_qc_readiness


def _install_fake_lean_loader(monkeypatch: pytest.MonkeyPatch, values: tuple[str, str]) -> None:
    lean_module = ModuleType("lean")
    commands_module = ModuleType("lean.commands")
    login_module = ModuleType("lean.commands.login")
    login_module.get_lean_config_credentials = lambda: values  # type: ignore[attr-defined]
    lean_module.commands = commands_module  # type: ignore[attr-defined]
    commands_module.login = login_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lean", lean_module)
    monkeypatch.setitem(sys.modules, "lean.commands", commands_module)
    monkeypatch.setitem(sys.modules, "lean.commands.login", login_module)


def test_qc_credentials_prefer_complete_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QC_USER_ID", "environment-user")
    monkeypatch.setenv("QC_API_TOKEN", "environment-token")
    _install_fake_lean_loader(monkeypatch, ("stored-user", "stored-token"))

    assert verify_qc_readiness._load_qc_credentials() == (
        "environment-user",
        "environment-token",
    )


def test_qc_credentials_use_official_lean_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QC_USER_ID", raising=False)
    monkeypatch.delenv("QC_API_TOKEN", raising=False)
    _install_fake_lean_loader(monkeypatch, ("stored-user", "stored-token"))

    assert verify_qc_readiness._load_qc_credentials() == ("stored-user", "stored-token")


def test_qc_credentials_fall_back_to_official_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("QC_USER_ID", raising=False)
    monkeypatch.delenv("QC_API_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    _install_fake_lean_loader(monkeypatch, ("", ""))
    credentials_path = tmp_path / ".lean" / "credentials"
    credentials_path.parent.mkdir()
    credentials_path.write_text(
        '{"user-id":"file-user","api-token":"file-token"}', encoding="utf-8"
    )

    assert verify_qc_readiness._load_qc_credentials() == ("file-user", "file-token")


def test_qc_credentials_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("QC_USER_ID", raising=False)
    monkeypatch.delenv("QC_API_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    _install_fake_lean_loader(monkeypatch, ("", ""))

    with pytest.raises(verify_qc_readiness.ExternalQCCredentialRequired):
        verify_qc_readiness._load_qc_credentials()


def test_authorized_runtime_files_fit_qc_cloud_limit() -> None:
    oversized = {
        name: (verify_qc_readiness.PROJECT_ROOT / name).stat().st_size
        for name in verify_qc_readiness._runtime_file_names()
        if (verify_qc_readiness.PROJECT_ROOT / name).stat().st_size > 32_000
    }

    assert oversized == {}
