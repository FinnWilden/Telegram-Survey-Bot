import importlib.util
import sys
from pathlib import Path
from zipfile import ZipFile


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "scripts"
    / "package_precompiled.py"
)


def test_packages_yaml_config_template(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("package_precompiled", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    root = tmp_path
    dist_dir = root / "dist"
    executable_dir = dist_dir / "Survey-Bot"
    executable_dir.mkdir(parents=True)
    (executable_dir / "Survey-Bot.exe").write_bytes(b"test executable")

    config_dir = root / "config"
    config_dir.mkdir()
    config_template = 'api_token: "YOUR_TELEGRAM_BOT_TOKEN"\n'
    (config_dir / "config.yml").write_text(config_template, encoding="utf-8")

    (root / "packaging").mkdir()
    (root / "packaging" / "PRECOMPILED-README.txt").write_text(
        "Instructions",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("License", encoding="utf-8")

    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "--platform",
            "windows",
            "--architecture",
            "x86_64",
        ],
    )

    module.main()

    archive_path = dist_dir / "Telegram-Survey-Bot-windows-x86_64.zip"
    with ZipFile(archive_path) as archive:
        packaged_config = archive.read("Telegram-Survey-Bot/config/config.yml").decode()
        assert packaged_config.splitlines() == config_template.splitlines()
        assert "Telegram-Survey-Bot/config/config.json" not in archive.namelist()
