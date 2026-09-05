"""
novelWriter - PyPI Build
========================

This file is a part of novelWriter
Copyright (C) 2026 Veronica Berglyd Olsen and novelWriter contributors

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
import shutil

from utils.common import ROOT_DIR, SETUP_DIR, copySourceCode, freshFolder, systemCall, updateMetaFile


def pypi(args: argparse.Namespace) -> None:
    """Build sdist and wheel packages for PyPI."""
    print("")
    print("Build PyPI Packages")
    print("===================")
    print("")

    bldDir = ROOT_DIR / "dist_pypi"
    outDir = bldDir / "novelwriter_src"

    bldDir.mkdir(exist_ok=True)
    freshFolder(outDir)

    print("Copying novelWriter source ...")
    print("")

    copySourceCode(outDir)
    updateMetaFile(outDir / "novelwriter" / "assets" / "meta.toml", buildFormat="pypi", installSource="pypi")

    print("")
    print("Copying additional files ...")
    print("")

    shutil.copyfile(ROOT_DIR / "pyproject.toml", outDir / "pyproject.toml")
    print("Copied: pyproject.toml")
    shutil.copyfile(ROOT_DIR / "LICENSE.md", outDir / "LICENSE.md")
    print("Copied: LICENSE.md")

    (outDir / "setup").mkdir(exist_ok=True)
    shutil.copyfile(SETUP_DIR / "description_pypi.md", outDir / "setup" / "description_pypi.md")
    print("Copied: setup/description_pypi.md")

    print("")
    print("Running uv build ...")
    print("")

    systemCall(["uv", "build", "--out-dir", str(bldDir), str(outDir)])
