"""
Hydra ETL — declarative ETL engine, CLI, API and Studio.

Copyright (C) 2026  Bechir Bejaoui

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or (at your
option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public
License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

This module holds the single source of truth for the product version.
Every other consumer reads it; none of them repeats it.

    setup.py / pyproject.toml   -> reads __version__
    hdrctl --version, banner    -> reads __version__
    GET /api/health             -> reads __version__
    Studio footer               -> reads it through the API

See "Règle 3 — Versionnage" in CLAUDE.md. A hard-coded version literal
anywhere else in the code base is a bug.

`DSL_VERSION` is a different number: it is the version of the manifest
format, the one written at the top of every YAML file. It only changes on a
breaking format change, and never follows the product version.
"""

__version__ = "0.10.2"
__license__ = "AGPL-3.0-or-later"
DSL_VERSION = "1.0"

__all__ = ["__version__", "__license__", "DSL_VERSION"]
