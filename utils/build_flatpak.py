"""
novelWriter - Flatpak Build
===========================

This file is a part of novelWriter
Copyright (C) 2025 Veronica Berglyd Olsen and novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""  # noqa

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import subprocess
import sys
import urllib.request

from pathlib import Path

from utils.common import (
    ROOT_DIR,
    appdataXml,
    extractBuildInfo,
    extractVersion,
    makeCheckSum,
    readFile,
    toUpload,
    writeFile,
)

PIP_GEN_COMMIT = "737c0085912f9f7dabf9341d4608e2a77a51a73a"
PIP_GEN_FILE = "pip/flatpak-pip-generator.py"
PIP_GEN_URL = f"https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/{PIP_GEN_COMMIT}/{PIP_GEN_FILE}"
ENCHANT_RELEASE_API = "https://api.github.com/repos/rrthomas/enchant/releases/tags/v{version}"
NW_REPO_URL = "https://github.com/vkbo/novelWriter.git"
NW_COMMIT_API = "https://api.github.com/repos/vkbo/novelWriter/commits/v{version}"
FLATHUB_FILES = ("io.novelwriter.novelwriter.yml", "pypi-deps.json", "enchant.json", "novelwriter.appdata.xml")


def processEnchant(bldDir: Path, enchantVersion: str) -> None:
    """Generate the enchant.json flatpak module for the pinned enchant version."""
    print("Generate Enchant Module")
    print("=======================")
    print("")

    outFile = bldDir / "enchant.json"

    try:
        fileName = f"enchant-{enchantVersion}.tar.gz"
        url = f"https://github.com/rrthomas/enchant/releases/download/v{enchantVersion}/{fileName}"

        apiUrl = ENCHANT_RELEASE_API.format(version=enchantVersion)
        print(f"Checking: {apiUrl}")
        with urllib.request.urlopen(apiUrl) as response:
            release = json.loads(response.read())

        assets = {a["name"]: a for a in release["assets"]}
        if fileName not in assets:
            raise ValueError(f"Asset '{fileName}' not found in release 'v{enchantVersion}'")
        checksum = assets[fileName]["digest"].removeprefix("sha256:")

        print(f"Version: {enchantVersion}")
        print(f"SHA256: {checksum}")

        module = {
            "name": "enchant",
            "buildsystem": "autotools",
            "post-install": [
                "install -Dm644 -T COPYING.LIB ${FLATPAK_DEST}/share/licenses/${FLATPAK_ID}/enchant-COPYING.LIB",
            ],
            "sources": [
                {
                    "type": "archive",
                    "url": url,
                    "sha256": checksum,
                },
            ],
        }
        writeFile(outFile, json.dumps(module, indent=4) + "\n")
    except Exception as exc:
        print("Generate Enchant Module: FAILED")
        print("")
        print(str(exc))
        sys.exit(1)

    print("")


def processDependencies(bldDir: Path) -> None:
    """Generate the pypi-deps.json file."""
    print("Generate PyPI Dependencies")
    print("==========================")
    print("")

    genScript = bldDir / "flatpak-pip-generator.py"
    outFile = bldDir / "pypi-deps"

    try:
        if not genScript.exists():
            print(f"Downloading: {PIP_GEN_URL}")
            urllib.request.urlretrieve(PIP_GEN_URL, genScript)

        print("")
        subprocess.run(
            [
                "uv",
                "run",
                str(genScript),
                "--pyproject-file",
                str(ROOT_DIR / "pyproject.toml"),
                "--ignore-pkg",
                "pyqt6",
                "-o",
                str(outFile),
            ],
            check=True,
        )
    except Exception as exc:
        print("Generate PyPI Dependencies: FAILED")
        print("")
        print(str(exc))
        sys.exit(1)
    finally:
        genScript.unlink(missing_ok=True)

    print("")


def flatpak(args: argparse.Namespace) -> None:
    """Build a flatpak bundle locally, for direct download."""
    print("")
    print("Build Flatpak")
    print("=============")
    print("")

    buildInfo = extractBuildInfo("flatpak")
    qtVersion = buildInfo["qt_version"]
    enchantVersion = buildInfo["enchant_version"]

    pkgVers, _, relDate = extractVersion()
    relDate = datetime.datetime.strptime(relDate, "%Y-%m-%d")

    bldDir = ROOT_DIR / "dist_flatpak"
    bldPkg = f"novelwriter_{pkgVers}"
    outDir = bldDir / bldPkg

    # Set Up Folders
    # ==============

    if outDir.exists():
        print("Removing old build files ...")
        print("")
        shutil.rmtree(outDir)

    bldDir.mkdir(exist_ok=True)
    outDir.mkdir(exist_ok=True)

    processDependencies(bldDir)
    processEnchant(bldDir, enchantVersion)
    writeFile(bldDir / "novelwriter.appdata.xml", appdataXml())

    template = readFile(ROOT_DIR / "setup" / "flatpak" / "io.novelwriter.novelwriter.yml")
    template = template.replace("@QT_VERSION@", qtVersion)
    template = template.replace("@FILESYSTEM_PERMISSION@", "home")
    manifestFile = bldDir / "io.novelwriter.novelwriter.yml"
    writeFile(manifestFile, template)

    # Build flatpak
    # ==============

    manifestPath = str(manifestFile)
    bundleFile = bldDir / f"novelwriter-{pkgVers}-linux.flatpak"

    try:
        subprocess.run(
            [
                "flatpak-builder",
                "--user",
                f"--repo={outDir}/repo",
                "--install-deps-from=flathub",
                "--force-clean",
                outDir,
                manifestPath,
            ],
            check=True,
        )
        subprocess.run(
            [
                "flatpak",
                "build-bundle",
                f"{outDir}/repo",
                bundleFile,
                "io.novelwriter.novelwriter",
            ],
            check=True,
        )
    except Exception as exc:
        print("Flatpak build: FAILED")
        print("")
        print(str(exc))
        print("")
        print("Dependencies:")
        print(" * flatpak flatpak-builder")
        print("")
        sys.exit(1)

    shaFile = makeCheckSum(bundleFile.name, cwd=bldDir)

    toUpload(bundleFile)
    toUpload(shaFile)


def flathub(args: argparse.Namespace) -> None:
    """Generate the manifest and support files for a Flathub submission."""
    # Import here so we can still run pkgutils with plain python
    import yaml

    print("")
    print("Build Flathub Submission")
    print("========================")
    print("")

    buildInfo = extractBuildInfo("flatpak")
    qtVersion = buildInfo["qt_version"]
    enchantVersion = buildInfo["enchant_version"]

    pkgVers, _, _ = extractVersion()
    tag = f"v{pkgVers}"

    bldDir = ROOT_DIR / "dist_flathub"
    bldDir.mkdir(exist_ok=True)

    processDependencies(bldDir)
    processEnchant(bldDir, enchantVersion)
    writeFile(bldDir / "novelwriter.appdata.xml", appdataXml())

    print("Resolve Release Commit")
    print("======================")
    print("")

    commitApiUrl = NW_COMMIT_API.format(version=pkgVers)
    try:
        print(f"Checking: {commitApiUrl}")
        with urllib.request.urlopen(commitApiUrl) as response:
            commit = json.loads(response.read())["sha"]
        print(f"Tag: {tag}")
        print(f"Commit: {commit}")
    except Exception as exc:
        print("Resolve Release Commit: FAILED")
        print("")
        print(str(exc))
        print("")
        print(f"Has version {pkgVers} been tagged and pushed to GitHub yet?")
        print("")
        sys.exit(1)

    print("")

    manifest = yaml.safe_load(readFile(ROOT_DIR / "setup" / "flatpak" / "io.novelwriter.novelwriter.yml"))
    manifest["runtime-version"] = qtVersion
    manifest["base-version"] = qtVersion
    manifest["finish-args"] = [
        "--filesystem=xdg-documents" if a.startswith("--filesystem=") else a for a in manifest["finish-args"]
    ]
    for module in manifest["modules"]:
        if isinstance(module, dict) and module.get("name") == "novelWriter":
            module["sources"] = [
                {"type": "git", "url": NW_REPO_URL, "tag": tag, "commit": commit},
                {"type": "file", "path": "novelwriter.appdata.xml"},
            ]
            break

    manifestFile = bldDir / "io.novelwriter.novelwriter.yml"
    with open(manifestFile, mode="w", encoding="utf-8") as outFile:
        yaml.safe_dump(manifest, outFile, sort_keys=False)
    print("Wrote:", manifestFile.relative_to(ROOT_DIR))
    print("")

    if path := args.path:
        dstDir = Path(path)
        if not dstDir.is_dir():
            print(f"Error: not a directory: {dstDir}")
            sys.exit(1)

        print(f"Copy Files to {dstDir}")
        print("=" * (len(str(dstDir)) + 14))
        print("")
        for name in FLATHUB_FILES:
            shutil.copyfile(bldDir / name, dstDir / name)
            print(f"Copied: {name}")
        print("")
    else:
        print(f"Flathub submission files written to {bldDir.relative_to(ROOT_DIR)}/")
        print("")
