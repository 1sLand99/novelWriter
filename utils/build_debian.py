"""
novelWriter - Debian Build
==========================

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
import email.utils
import os
import shutil
import sys

from dataclasses import dataclass
from pathlib import Path

from utils.common import (
    MIN_PY_VERSION,
    MIN_QT_VERS,
    ROOT_DIR,
    SETUP_DIR,
    checkAssetsExist,
    copyPackageFiles,
    copySourceCode,
    copyTestCode,
    extractVersion,
    makeCheckSum,
    systemCall,
    toUpload,
    writeFile,
)

SIGN_KEY = "D6A9F6B8F227CF7C6F6D1EE84DBBE4B734B0BD08"

DEB_CONTROL = f"""
Source: novelwriter
Maintainer: Veronica Berglyd Olsen <code@vkbo.net>
Section: text
Priority: optional
Build-Depends:
  dh-python,
  pybuild-plugin-pyproject,
  python3-build,
  python3-setuptools,
  python3-all,
  debhelper (>= 9),
  %dependencies%,
  %test-dependencies%
Standards-Version: 4.5.1
Homepage: https://novelwriter.io
X-Python3-Version: >= {MIN_PY_VERSION}

Package: novelwriter
Architecture: all
Depends:
  ${{misc:Depends}},
  ${{python3:Depends}},
  %dependencies%
Description: A plain text editor for planning and writing novels
"""


@dataclass(frozen=True)
class DistroTarget:
    """A single Debian/Ubuntu distro release to build a package for."""

    family: str
    codename: str
    numVersion: str
    debianVersion: int
    image: str
    suffix: str
    oldLicense: bool = False


DISTRO_TARGETS: dict[str, DistroTarget] = {
    "bookworm": DistroTarget("debian", "bookworm", "12", 12, "debian:12", "bookworm"),
    "trixie": DistroTarget("debian", "trixie", "13", 13, "debian:13", "trixie"),
    "noble": DistroTarget("ubuntu", "noble", "24.04", 12, "ubuntu:24.04", "ubuntu24.04", oldLicense=True),
    "resolute": DistroTarget("ubuntu", "resolute", "26.04", 13, "ubuntu:26.04", "ubuntu26.04"),
    "stonking": DistroTarget("ubuntu", "stonking", "26.10", 13, "ubuntu:26.10", "ubuntu26.10"),
}


def makeDebianPackage(
    signKey: str | None = None,
    sourceBuild: bool = False,
    distName: str = "unstable",
    buildName: str = "",
    debianVersion: int = 13,
    oldLicense: bool = False,
    prebuiltWheel: Path | None = None,
) -> str:
    """Build a Debian package."""
    print("")
    print("Build Debian Package")
    print("====================")
    print("On Debian/Ubuntu install: dh-python python3-all debhelper devscripts ")
    print("                          pybuild-plugin-pyproject")
    print("")

    # Version Info
    # ============

    numVers, hexVers, relDate = extractVersion()
    relDate = datetime.datetime.strptime(relDate, "%Y-%m-%d")
    pkgDate = email.utils.format_datetime(relDate.replace(hour=12, tzinfo=None))
    print("")

    # Use a tilde before pre-release identifiers so they sort before the
    # final release in dpkg/apt version comparisons, regardless of distro.
    pkgVers = numVers.replace("a", "~a").replace("b", "~b").replace("rc", "~rc")

    pkgVers = f"{pkgVers}+{buildName}" if buildName else pkgVers

    # Set Up Folder
    # =============

    bldDir = ROOT_DIR / "dist_deb"
    bldPkg = f"novelwriter_{pkgVers}"
    outDir = bldDir / bldPkg
    debDir = outDir / "debian"
    datDir = outDir / "data"

    bldDir.mkdir(exist_ok=True)
    if outDir.exists():
        print("Removing old build files ...")
        print("")
        shutil.rmtree(outDir)

    outDir.mkdir(exist_ok=False)

    # Check Additional Assets
    # =======================

    if not checkAssetsExist():
        print("ERROR: Missing build assets")
        sys.exit(1)

    # Copy novelWriter Source
    # =======================

    print("Copying novelWriter source ...")
    print("")

    copySourceCode(outDir)
    copyTestCode(outDir)

    print("")
    print("Copying or generating additional files ...")
    print("")

    copyPackageFiles(outDir, oldLicense=oldLicense)

    # Copy/Write Debian Files
    # =======================

    shutil.copytree(SETUP_DIR / "debian", debDir)
    print("Copied: debian/*")

    depend = [
        f"python3 (>= {MIN_PY_VERSION})",
        f"python3-pyqt6 (>= {MIN_QT_VERS})",
        f"python3-pyqt6.qtsvg (>= {MIN_QT_VERS})",
        "python3-enchant (>= 2.0)",
        f"qt6-image-formats-plugins (>= {MIN_QT_VERS})",
    ]
    if debianVersion > 12:
        depend.append(f"qt6-svg-plugins (>= {MIN_QT_VERS})")

    testDepend = [
        "python3-pytest (>= 6.0)",
        "python3-pytestqt",
        "python3-pytest-timeout",
    ]

    control = DEB_CONTROL.replace("%dependencies%", ",\n  ".join(depend))
    control = control.replace("%test-dependencies%", ",\n  ".join(testDepend))
    writeFile(debDir / "control", control)
    print("Wrote:  debian/control")

    writeFile(
        debDir / "changelog",
        (
            f"novelwriter ({pkgVers}) {distName}; urgency=low\n\n"
            f"  * Update to version {pkgVers}\n\n"
            f" -- Veronica Berglyd Olsen <code@vkbo.net>  {pkgDate}\n"
        ),
    )
    print("Wrote:  debian/changelog")

    # Copy/Write Data Files
    # =====================

    shutil.copytree(SETUP_DIR / "data", datDir)
    print("Copied: data/*")

    shutil.copyfile(SETUP_DIR / "description_short.txt", outDir / "data" / "description_short.txt")
    print("Copied: data/description_short.txt")

    # Copy Prebuilt Wheel
    # ===================

    buildEnv = None
    if prebuiltWheel is not None:
        wheelDir = outDir / "dist"
        wheelDir.mkdir(exist_ok=True)
        wheelDst = wheelDir / prebuiltWheel.name
        shutil.copyfile(prebuiltWheel, wheelDst)
        print(f"Copied: {prebuiltWheel} -> dist/{prebuiltWheel.name}")
        buildEnv = {**os.environ, "NW_PREBUILT_WHEEL": str(wheelDst)}

    # Build Package
    # =============

    print("")
    print("Running dpkg-buildpackage ...")
    print("")

    if signKey is None:
        signArgs = ["-us", "-uc"]
    else:
        signArgs = [f"-k{signKey}"]

    if prebuiltWheel is not None:
        # Build-Depends are not installed when reusing a prebuilt wheel.
        signArgs = [*signArgs, "-d"]

    if sourceBuild:
        systemCall(["debuild", "-S", *signArgs], cwd=outDir, env=buildEnv)
        toUpload(bldDir / f"{bldPkg}.tar.xz")
    else:
        systemCall(["dpkg-buildpackage", *signArgs], cwd=outDir, env=buildEnv)
        shutil.copyfile(bldDir / f"{bldPkg}.tar.xz", bldDir / f"{bldPkg}.debian.tar.xz")
        toUpload(bldDir / f"{bldPkg}.debian.tar.xz")
        toUpload(bldDir / f"{bldPkg}_all.deb")
        toUpload(makeCheckSum(f"{bldPkg}.debian.tar.xz", cwd=bldDir))
        toUpload(makeCheckSum(f"{bldPkg}_all.deb", cwd=bldDir))

    print("")
    print("Done!")
    print("")

    if sourceBuild:
        ppaName = "novelwriter" if hexVers[-2] == "f" else "novelwriter-pre"
        return f"dput {ppaName}/{distName} {bldDir}/{bldPkg}_source.changes"

    return ""


def debian(args: argparse.Namespace) -> None:
    """Build a .deb package for a single distro target."""
    if sys.platform != "linux":
        print("ERROR: Command 'build-deb' can only be used on Linux")
        sys.exit(1)

    target = DISTRO_TARGETS[args.distro]

    wheel = Path(args.wheel) if args.wheel else None
    signKey = None if wheel is not None else (SIGN_KEY if args.sign else None)

    buildName = ""
    if args.with_suffix:
        bldNum = str(args.build) if args.build else "0"
        buildName = f"{target.suffix}.{bldNum}"

    makeDebianPackage(
        signKey,
        sourceBuild=False,
        distName=target.codename,
        buildName=buildName,
        debianVersion=target.debianVersion,
        oldLicense=False if wheel is not None else target.oldLicense,
        prebuiltWheel=wheel,
    )


def launchpad(args: argparse.Namespace) -> None:
    """Build Debian packages for Launchpad."""
    if sys.platform != "linux":
        print("ERROR: Command 'build-ubuntu' can only be used on Linux")
        sys.exit(1)

    print("")
    print("Launchpad Packages")
    print("==================")
    print("")

    if args.build:
        bldNum = str(args.build)
    else:
        bldNum = "0"

    distLoop = [
        ("24.04", "noble", 12, True),
        ("26.04", "resolute", 13, False),
        ("26.10", "stonking", 13, False),
    ]

    print("Building Ubuntu packages for:")
    print("")
    for distNum, codeName, _, _ in distLoop:
        print(f" * Ubuntu {distNum} {codeName.title()}")
    print("")

    signKey = SIGN_KEY if args.sign else None

    print(f"Sign Key: {signKey!s}")
    print("")

    dputCmd = []
    for distNum, codeName, debVer, oldLicense in distLoop:
        buildName = f"ubuntu{distNum}.{bldNum}"
        dCmd = makeDebianPackage(
            signKey=signKey,
            sourceBuild=True,
            distName=codeName,
            buildName=buildName,
            debianVersion=debVer,
            oldLicense=oldLicense,
        )
        dputCmd.append(dCmd)

    print("Packages Built")
    print("==============")
    print("")
    for dCmd in dputCmd:
        print(f" > {dCmd}")
    print("")
