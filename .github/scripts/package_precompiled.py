from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True)
    parser.add_argument("--architecture", required=True)
    args = parser.parse_args()

    dist_dir = ROOT / "dist"
    executable_dir = dist_dir / "Survey-Bot"
    if not executable_dir.is_dir():
        raise FileNotFoundError(f"PyInstaller output not found: {executable_dir}")

    config_template = ROOT / "config" / "config.json"
    config = json.loads(config_template.read_text(encoding="utf-8"))
    if config.get("api_token") != "your_api_token_here":
        raise ValueError("The packaged config template must contain only the token placeholder")

    platform = args.platform.lower()
    architecture = args.architecture.lower()
    archive_path = dist_dir / f"Telegram-Survey-Bot-{platform}-{architecture}.zip"

    with tempfile.TemporaryDirectory(dir=dist_dir, prefix="precompiled-") as temp_dir:
        package_root = Path(temp_dir) / "Telegram-Survey-Bot"
        shutil.copytree(executable_dir, package_root)

        (package_root / "config").mkdir()
        shutil.copy2(config_template, package_root / "config" / "config.json")
        (package_root / "db").mkdir()
        (package_root / "log").mkdir()
        shutil.copy2(ROOT / "LICENSE", package_root / "LICENSE")
        shutil.copy2(
            ROOT / "packaging" / "PRECOMPILED-README.txt",
            package_root / "README.txt",
        )

        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(package_root.rglob("*")):
                archive_path_in_zip = path.relative_to(temp_dir).as_posix()
                if path.is_dir():
                    archive.writestr(f"{archive_path_in_zip}/", "")
                else:
                    archive.write(path, archive_path_in_zip)

    print(f"Created {archive_path}")


if __name__ == "__main__":
    main()
