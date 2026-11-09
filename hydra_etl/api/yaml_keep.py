"""
Écriture des YAML d'un projet par Studio, sans abîmer ce que l'utilisateur a écrit.

Studio produit chaque fichier à partir de son modèle (forme « canonique » :
guillemets simples, listes en bloc, aucun commentaire). Écrire ce texte tel quel
effaçait les commentaires, la mise en forme et les clés que Studio ne connaît
pas, même quand rien n'avait changé. Ici :

1. même contenu (après retrait des ajouts par défaut de Studio) → le fichier
   n'est pas réécrit, octet pour octet ;
2. contenu modifié → le texte de Studio est écrit, mais chaque ligne dont la
   valeur n'a pas changé reprend la ligne d'origine (guillemets, liste en ligne,
   commentaire de fin de ligne), et les commentaires placés au-dessus d'une clé
   restent au-dessus d'elle ;
3. workflow : la `description` du fichier est gardée (le canvas ne l'édite pas) ;
   `trigger: {type: manual}` (défaut) n'est pas ajouté s'il n'y était pas.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from hydra_etl.internal.fs_atomic import atomic_write_text

_KEY_RE = re.compile(r"^(\s*)(-\s+)?([A-Za-z_][\w.\-]*|\"[^\"]*\"|'[^']*')\s*:(?:\s+(.*?))?\s*$")
_ITEM_RE = re.compile(r"^(\s*)-\s+(.*?)\s*$")
_MISSING = object()


def _load(text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return _MISSING


def _strip_comment(value: str) -> Tuple[str, str]:
    """« valeur  # commentaire » → (valeur, « # commentaire ») ; ignore # entre guillemets."""
    quote = None
    for i, ch in enumerate(value):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or value[i - 1] in " \t"):
            return value[:i].rstrip(), value[i:]
    return value, ""


def _scan(text: str) -> List[Tuple[Optional[tuple], str, str, str]]:
    """Pour chaque ligne : (chemin de clés, valeur sans commentaire, commentaire, ligne).

    Chemin = clés de mapping et indices de liste depuis la racine, ex.
    ('sources', 'app', 'connection', 'host') ou ('steps', 0, 'filter', 'expr').
    None pour les lignes vides, de commentaire ou de texte multiligne."""
    out: List[Tuple[Optional[tuple], str, str, str]] = []
    stack: List[Tuple[int, Any]] = []          # (indentation, composant de chemin)
    counters: Dict[Tuple[tuple, int], int] = {}
    block_indent: Optional[int] = None         # dans un texte « | » ou « > »
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if block_indent is not None:
            if stripped and indent <= block_indent:
                block_indent = None
            else:
                out.append((None, "", "", line))
                continue
        if not stripped or stripped.startswith("#") or stripped in ("---", "..."):
            out.append((None, "", "", line))
            continue
        m = _KEY_RE.match(line)
        item = _ITEM_RE.match(line)
        if m:
            dash = m.group(2)
            key = m.group(3).strip("\"'")
            raw = m.group(4) or ""
            if dash:
                item_indent = indent
                while stack and stack[-1][0] >= item_indent:
                    stack.pop()
                parent = tuple(p for _, p in stack)
                idx = counters.get((parent, item_indent), -1) + 1
                counters[(parent, item_indent)] = idx
                stack.append((item_indent, idx))
                key_indent = item_indent + len(dash)
            else:
                key_indent = indent
                while stack and stack[-1][0] >= key_indent:
                    stack.pop()
            stack.append((key_indent, key))
            path = tuple(p for _, p in stack)
            value, comment = _strip_comment(raw)
            if value in ("|", ">", "|-", ">-", "|+", ">+"):
                block_indent = key_indent
            out.append((path, value, comment, line))
            # les entrées d'une liste sous cette clé repartent de 0
            counters = {k: v for k, v in counters.items() if k[0][:len(path)] != path}
        elif item:
            item_indent = indent
            while stack and stack[-1][0] >= item_indent:
                stack.pop()
            parent = tuple(p for _, p in stack)
            idx = counters.get((parent, item_indent), -1) + 1
            counters[(parent, item_indent)] = idx
            value, comment = _strip_comment(item.group(2))
            out.append((parent + (idx,), value, comment, line))
            stack.append((item_indent, idx))
        else:
            out.append((None, "", "", line))
    return out


def _get(data: Any, path: tuple) -> Any:
    for p in path:
        if isinstance(p, int):
            if not isinstance(data, list) or p >= len(data):
                return _MISSING
            data = data[p]
        else:
            if not isinstance(data, dict) or p not in data:
                return _MISSING
            data = data[p]
    return data


def _keep_lines(old_text: str, new_text: str) -> str:
    """Texte de Studio, avec les lignes d'origine pour ce qui n'a pas changé."""
    old_data, new_data = _load(old_text), _load(new_text)
    if old_data is _MISSING or new_data is _MISSING:
        return new_text
    old_lines = _scan(old_text)
    by_path: Dict[tuple, int] = {}
    for i, (path, _, _, _) in enumerate(old_lines):
        if path is not None and path not in by_path:
            by_path[path] = i
    out: List[str] = []
    new_lines = _scan(new_text)
    skip_under: Optional[Tuple[tuple, int]] = None
    for path, value, _, line in new_lines:
        if skip_under is not None:
            p, ind = skip_under
            if path is not None and path[:len(p)] == p and len(path) > len(p):
                continue                      # sous-arbre remplacé par la ligne d'origine
            if path is None and line.strip() and (len(line) - len(line.lstrip())) > ind:
                continue
            skip_under = None
        if path is None:
            out.append(line)
            continue
        oi = by_path.get(path)
        if oi is None:
            out.append(line)
            continue
        # commentaires placés juste au-dessus de la clé d'origine (en-tête compris)
        j, above = oi - 1, []
        while j >= 0 and old_lines[j][0] is None and (old_lines[j][3].strip().startswith("#")
                                                     or not old_lines[j][3].strip()):
            above.insert(0, old_lines[j][3])
            j -= 1
        while above and not above[0].strip():
            above.pop(0)
        if any(l.strip() for l in above) and out[-len(above):] != above:
            out.extend(above)
        old_line = old_lines[oi][3]
        old_value = old_lines[oi][1]
        same = _get(old_data, path) == _get(new_data, path) and _get(new_data, path) is not _MISSING
        if same and old_value not in ("|", ">", "|-", ">-", "|+", ">+"):
            indent_new = len(line) - len(line.lstrip(" "))
            indent_old = len(old_line) - len(old_line.lstrip(" "))
            out.append(" " * indent_new + old_line.lstrip(" ") if indent_new != indent_old else old_line)
            if old_value and not value:
                skip_under = (path, indent_new)      # liste/objet en ligne à l'origine
            elif value == "" and old_value == "":
                pass
            continue
        out.append(line)
    text = "\n".join(out)
    return text + ("\n" if new_text.endswith("\n") else "")


def _drop_studio_defaults(kind: str, old: Any, new: Any, job_name: str = "") -> Any:
    """Retire du nouveau contenu ce que Studio ajoute par défaut et que le fichier n'avait pas."""
    if not isinstance(new, dict):
        return new
    new = copy.deepcopy(new)
    old = old if isinstance(old, dict) else {}
    if kind == "pipeline":
        np, op = new.get("pipeline"), old.get("pipeline") or {}
        if isinstance(np, dict) and "name" not in op and np.get("name") in (job_name, None, ""):
            np.pop("name", None)
    if kind == "workflow":
        nw, ow = new.get("workflow"), old.get("workflow") or {}
        if isinstance(nw, dict):
            if "trigger" not in ow and nw.get("trigger") in ({"type": "manual"}, {"type": "manual", "cron": None}):
                nw.pop("trigger", None)
            if "description" in ow and "description" not in nw:
                # à sa place d'origine : juste après le nom
                items = list(nw.items())
                at = next((i + 1 for i, (k, _) in enumerate(items) if k == "name"), 0)
                items.insert(at, ("description", ow["description"]))
                new["workflow"] = dict(items)
    return new


def write_yaml_keeping(path: Path, new_text: str, *, kind: str = "", job_name: str = "") -> bool:
    """Écrit `new_text` dans `path` en gardant ce que l'utilisateur a écrit.
    Renvoie False si le fichier n'avait pas à changer (rien n'est écrit)."""
    path = Path(path)
    old_text = path.read_text(encoding="utf-8-sig") if path.is_file() else None
    new_data = _load(new_text)
    if old_text is None:
        atomic_write_text(path, new_text)
        return True
    old_data = _load(old_text)
    if new_data is _MISSING:
        atomic_write_text(path, new_text)
        return True
    cleaned = _drop_studio_defaults(kind, old_data, new_data, job_name)
    if old_data is not _MISSING and cleaned == old_data:
        return False                                   # même contenu : fichier intact
    if cleaned != new_data:
        new_text = yaml.safe_dump(cleaned, sort_keys=False, allow_unicode=True)
    atomic_write_text(path, _keep_lines(old_text, new_text))
    return True
