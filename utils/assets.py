"""
novelWriter - Assets
====================

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
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

from pathlib import Path

from utils.common import ROOT_DIR, log, writeFile
from utils.docs import buildPdfDocAssets


def _normaliseTsLocations(tsFile: Path) -> tuple[int, int]:
    """Strip volatile TS line locations and merge duplicate file locations."""
    tree = ET.parse(tsFile)
    root = tree.getroot()

    nLines = 0
    nMerged = 0

    for message in root.findall("./context/message"):
        seenFiles: set[str] = set()
        for location in list(message.findall("location")):
            if "line" in location.attrib:
                del location.attrib["line"]
                nLines += 1

            if (filename := location.attrib.get("filename", "")) in seenFiles:
                message.remove(location)
                nMerged += 1
            else:
                seenFiles.add(filename)

    if nLines > 0 or nMerged > 0:
        ET.indent(tree, space="  ")
        header = '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
        xmlBody = ET.tostring(root, encoding="unicode", short_empty_elements=True)
        xmlBody = xmlBody.replace(" />", "/>")  # Remove space before self-closing tags
        tsFile.write_text(f"{header}{xmlBody}\n", encoding="utf-8")

    return nLines, nMerged


def _validateProjectTranslation(path: Path, expected: int, threshold: float) -> None:
    """Validate a project translation file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (translated := len(data) / expected) >= threshold:
            log(f"[cg]Accepted:[e] [cw]{100 * translated:5.1f}%[e] {path.name}")
        else:
            log(f"[cr]Rejected:[e] [cw]{100 * translated:5.1f}%[e] {path.name}")
            path.unlink()
    except Exception:
        log(f"[cr]ERROR:[e] Could not process file {path}")


def _validateTsTranslation(path: Path, expected: int, threshold: float) -> None:
    """Validate a Qt Linguist translation file."""
    try:
        root = ET.parse(path).getroot()
        unfinished = len(root.findall('.//translation[@type="unfinished"]'))
        if (translated := (expected - unfinished) / expected) >= threshold:
            log(f"[cg]Accepted:[e] [cw]{100 * translated:5.1f}%[e] {path.name}")
        else:
            log(f"[cr]Rejected:[e] [cw]{100 * translated:5.1f}%[e] {path.name}")
            path.unlink()
    except Exception:
        log(f"[cr]ERROR:[e] Could not process file {path}")


def buildSampleZip(args: argparse.Namespace | None = None) -> None:
    """Bundle the sample project into a single zip file to be saved into
    the novelwriter/assets folder for further bundling into builds.
    """
    log("")
    log("[b]Building Sample ZIP File[e]")
    log("[b]========================[e]")
    log("")

    srcSample = ROOT_DIR / "sample"
    dstSample = ROOT_DIR / "novelwriter" / "assets" / "sample.zip"

    if srcSample.is_dir():
        dstSample.unlink(missing_ok=True)
        with zipfile.ZipFile(dstSample, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as zipObj:
            log("[cg]Compressing:[e] nwProject.nwx")
            zipObj.write(srcSample / "nwProject.nwx", "nwProject.nwx")
            for doc in (srcSample / "content").iterdir():
                log(f"[cg]Compressing:[e] content/{doc.name}")
                zipObj.write(doc, f"content/{doc.name}")

    else:
        log("[cr]Error:[e] Could not find sample project source directory.")
        sys.exit(1)

    log("")
    log(f"[cg]Built file:[e] {dstSample}")
    log("")


def importI18nUpdates(args: argparse.Namespace) -> None:
    """Import new translation files from a zip file."""
    log("")
    log("[b]Import Updated Translations[e]")
    log("[b]===========================[e]")

    fileName = Path(args.file).absolute()
    log(f"[b]Archive:[e] {fileName}")
    if not fileName.is_file():
        log("[cr]File not found ...[e]")
        sys.exit(1)
    log("")

    dstPath = ROOT_DIR / "novelwriter" / "assets" / "i18n"
    srcPath = ROOT_DIR / "i18n"

    threshold = args.threshold / 100
    expected_json = len(json.loads((dstPath / "project_en_GB.json").read_text(encoding="utf-8")))
    expected_ts = len(ET.parse(srcPath / "nw_base.ts").getroot().findall(".//message"))

    with zipfile.ZipFile(fileName) as zipObj:
        for item in zipObj.namelist():
            if item == "nw_base.ts":
                log(f"[cy]Skipped:[e] {item}")
            elif item.startswith("nw_") and item.endswith(".ts"):
                zipObj.extract(item, srcPath)
                _validateTsTranslation(srcPath / item, expected_ts, threshold)
            elif item.startswith("project_") and item.endswith(".json"):
                zipObj.extract(item, dstPath)
                _validateProjectTranslation(dstPath / item, expected_json, threshold)
            else:
                log(f"[cy]Skipped:[e] {item}")

    log("")


def updateTranslationSources(args: argparse.Namespace) -> None:
    """Build the lang.ts files for Qt Linguist."""
    log("")
    log("[b]Building Qt Translation Files[e]")
    log("[b]=============================[e]")

    try:
        from PyQt6.lupdate.lupdate import lupdate
    except ImportError:
        log("[cr]ERROR: This command requires lupdate from PyQt6[e]")
        log("[cy]On Debian/Ubuntu, install: pyqt6-dev-tools[e]")
        sys.exit(1)

    log("")
    log("[b]Scanning Source Tree:[e]")
    log("")

    sources = list((ROOT_DIR / "novelwriter").glob("**/*.py"))
    for source in sources:
        log(source.relative_to(ROOT_DIR))

    log("")
    log("[b]TS Files to Update:[e]")
    log("")

    translations = []
    for item in [Path(str(f)).absolute() for f in args.files]:
        if not (item.name.startswith("nw_") and item.suffix == ".ts"):
            log(f"[cy]Skipped:[e] {item}")
            continue

        if item.is_file():
            translations.append(item)
            log(f"[cg]Added:[e] {item}")
        elif item.exists():
            continue
        else:  # Create an empty new language file
            langCode = item.name[3:-3]
            writeFile(
                item,
                (
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    "<!DOCTYPE TS>\n"
                    f'<TS version="2.0" language="{langCode}" sourcelanguage="en_GB"/>\n'
                ),
            )
            translations.append(item)
            log(f"[cg]Created:[e] {item}")

    log("")
    log("[b]Updating Language Files:[e]")
    log("")

    lupdate(
        sources=[str(f) for f in sources],
        translation_files=[str(f) for f in translations],
        no_obsolete=True,
        no_summary=False,
    )

    log("")
    log("[b]Normalising TS Location Metadata:[e]")
    log("")

    for item in translations:
        nLines, nMerged = _normaliseTsLocations(item)
        if nLines > 0 or nMerged > 0:
            log(f"[cg]Updated:[e] {item} ({nLines} line refs, {nMerged} merged)")
        else:
            log(f"[cy]No Change:[e] {item}")

    log("")


def getLReleaseExec() -> str | None:
    """Look for the lrelease executable."""
    for entry in ["lrelease-qt6", "lrelease"]:
        if subprocess.call(f"type {entry}", shell=True) == 0:
            return entry
    return None


def buildTranslationAssets(args: argparse.Namespace | None = None) -> None:
    """Build the lang.qm files for Qt Linguist."""
    log("")
    log("[b]Building Qt Localisation Files[e]")
    log("[b]==============================[e]")

    log("")
    log("[b]TS Files to Build:[e]")
    log("")

    srcDir = ROOT_DIR / "i18n"
    dstDir = ROOT_DIR / "novelwriter" / "assets" / "i18n"

    srcList = []
    for item in srcDir.iterdir():
        if item.is_file() and item.suffix == ".ts" and item.name != "nw_base.ts":
            srcList.append(item)
            log(item)

    log("")
    log("[b]Building Translation Files:[e]")
    log("")

    try:
        if lrelease := getLReleaseExec():
            subprocess.call([lrelease, "-verbose", *srcList])
        else:
            raise FileNotFoundError("No lrelease executable found")
    except Exception as exc:
        log("[cy]Qt Linguist tools seem to be missing[e]")
        log("[cy]On Debian/Ubuntu, install: qttools5-dev-tools[e]")
        log(exc)
        sys.exit(1)

    log("")
    log("[b]Moving QM Files to Assets[e]")
    log("")

    dstRel = dstDir.relative_to(ROOT_DIR)
    for item in srcDir.iterdir():
        if item.is_file() and item.suffix == ".qm":
            item.rename(dstDir / item.name)
            log(f"[cg]Moved:[e] {item.relative_to(ROOT_DIR)} -> {dstRel / item.name}")

    log("")


def cleanBuiltAssets(args: argparse.Namespace | None = None) -> None:
    """Remove assets built by this script."""
    log("")
    log("[b]Removing Built Assets[e]")
    log("[b]=====================[e]")
    log("")

    assets = [ROOT_DIR / "novelwriter" / "assets" / "sample.zip"]
    assets.extend((ROOT_DIR / "novelwriter" / "assets").glob("manual*.pdf"))
    assets.extend((ROOT_DIR / "novelwriter" / "assets" / "i18n").glob("*.qm"))
    for asset in assets:
        if asset.is_file():
            asset.unlink()
            log(f"[cy]Deleted:[e] {asset.relative_to(ROOT_DIR)}")

    log("")


def buildAllAssets(args: argparse.Namespace) -> None:
    """Build all assets."""
    cleanBuiltAssets()
    buildSampleZip()
    buildTranslationAssets()
    buildPdfDocAssets()
