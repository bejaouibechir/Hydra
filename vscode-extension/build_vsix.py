#!/usr/bin/env python3
"""
Build the .vsix package of the HYDRA ETL extension, without npm or vsce.

A .vsix is a ZIP archive holding:
    [Content_Types].xml       MIME type declarations
    extension.vsixmanifest    metadata VS Code reads at install time
    extension/                the actual extension payload

Usage:
    python build_vsix.py

Then:
    code --install-extension "hydra-etl-0.1.2.vsix"
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent

# Directories and files kept out of the package (mirrors .vscodeignore)
EXCLUDE_DIRS = {"examples", "node_modules", ".git", ".vscode", "__pycache__"}
EXCLUDE_FILES = {".vscodeignore", "build_vsix.py", "icon@256.png"}
EXCLUDE_SUFFIXES = {".vsix", ".pyc"}

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="md" ContentType="text/markdown" />
  <Default Extension="xml" ContentType="text/xml" />
  <Default Extension="vsixmanifest" ContentType="text/xml" />
  <Default Extension="png" ContentType="image/png" />
  <Default Extension="yaml" ContentType="text/yaml" />
</Types>
"""


def build_manifest(pkg: dict) -> str:
    """Generate extension.vsixmanifest from package.json."""
    deps = ",".join(pkg.get("extensionDependencies", []))
    tags = ",".join(pkg.get("keywords", []))
    cats = ",".join(pkg.get("categories", []))
    engine = pkg.get("engines", {}).get("vscode", "^1.75.0")

    # The icon is only declared when the file actually exists,
    # otherwise VS Code rejects the package.
    icon_asset = ""
    icon_rel = pkg.get("icon")
    if icon_rel and (ROOT / icon_rel).exists():
        icon_asset = (
            '\n    <Asset Type="Microsoft.VisualStudio.Services.Icons.Default"\n'
            f'           Path="extension/{escape(icon_rel)}" Addressable="true" />'
        )

    banner = pkg.get("galleryBanner", {})
    banner_props = ""
    if banner:
        banner_props = (
            f'\n      <Property Id="Microsoft.VisualStudio.Services.Branding.Color"'
            f' Value="{escape(banner.get("color", "#000000"))}" />'
            f'\n      <Property Id="Microsoft.VisualStudio.Services.Branding.Theme"'
            f' Value="{escape(banner.get("theme", "dark"))}" />'
        )

    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0"
    xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"
    xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US"
              Id="{escape(pkg['name'])}"
              Version="{escape(pkg['version'])}"
              Publisher="{escape(pkg['publisher'])}" />
    <DisplayName>{escape(pkg['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(pkg['description'])}</Description>
    <Tags>{escape(tags)}</Tags>
    <Categories>{escape(cats)}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(engine)}" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="{escape(deps)}" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui,workspace" />{banner_props}
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest"
           Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details"
           Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Changelog"
           Path="extension/CHANGELOG.md" Addressable="true" />{icon_asset}
  </Assets>
</PackageManifest>
"""


def collect_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.name in EXCLUDE_FILES or path.suffix in EXCLUDE_SUFFIXES:
            continue
        files.append(path)
    return files


def main() -> int:
    pkg_path = ROOT / "package.json"
    if not pkg_path.exists():
        sys.exit("package.json not found.")

    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    out = ROOT / f"{pkg['name']}-{pkg['version']}.vsix"

    files = collect_files()
    if not files:
        sys.exit("Nothing to package.")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("extension.vsixmanifest", build_manifest(pkg))
        for path in files:
            arc = "extension/" + path.relative_to(ROOT).as_posix()
            z.write(path, arc)

    size_kb = out.stat().st_size / 1024
    print(f"Package built: {out.name}  ({size_kb:.1f} KB, {len(files) + 2} entries)")
    for path in files:
        print(f"  extension/{path.relative_to(ROOT).as_posix()}")
    print("\nInstall with:")
    print(f'  code --install-extension "{out}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
