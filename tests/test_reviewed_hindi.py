"""Every Hindi line the coach says or shows is one a native speaker reviewed, or a draft listed here.

reviewed_hindi.json pins each reviewed line by a hash of its text, found by where it is in phrases.py and checkin.py
(a table's keys, or a function's strings in order). A reviewed line that changes, or a new line that isn't a draft,
fails until it's reviewed again with the user. After a review, refresh the pins:

    uv run python tests/test_reviewed_hindi.py --pin

The pins hold the user's review of Oct 29, 2026: review page ec5466828411 with its one change, three lines approved after
it, then the lines for a photo without lens data, the Listen button and the read-back's shapes, and (Nov 4) the two
lens buttons, the answers the reviewed lens question asks for, and the verdict «सीडीसी की सलाह के मुताबिक», a part of
the reviewed meets line. index.html's Hindi is phrases.PAGE's (test_web checks the two match).
"""

import ast
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("src/aftermath/phrases.py", "src/aftermath/checkin.py")
PINS = Path(__file__).with_name("reviewed_hindi.json")
DEVANAGARI = re.compile("[ऀ-ॿ]")

# Hindi written after the last review, until the user approves it and it's pinned: none now. DRAFT_FUNCTIONS holds
# "module.function#" prefixes, for a function whose strings are all new.
DRAFTS: set[str] = set()
DRAFT_FUNCTIONS: tuple[str, ...] = ()


def hindi_lines() -> dict[str, str]:
    """Every string with Hindi in it, by where it is ("phrases.PHRASES[fresh-air-now][hi]", "phrases.read_back#1")."""
    found: dict[str, str] = {}
    for source in SOURCES:
        module = Path(source).stem
        tree = ast.parse((ROOT / source).read_text(encoding="utf-8"))
        docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                      if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(node)}
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                target = node.targets[0] if isinstance(node, ast.Assign) else node.target
                walk(node.value, f"{module}.{ast.unparse(target)}", found, docstrings)
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                pieces(node, f"{module}.{node.name}", found, docstrings)
    return found


def walk(node: ast.AST, path: str, found: dict, docstrings: set) -> None:
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            label = key.value if isinstance(key, ast.Constant) else ast.unparse(key) if key is not None else "**"
            walk(value, f"{path}[{label}]", found, docstrings)
    elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for i, item in enumerate(node.elts):
            walk(item, f"{path}[{i}]", found, docstrings)
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        if DEVANAGARI.search(node.value):
            found[path] = node.value
    else:
        pieces(node, path, found, docstrings)


def pieces(node: ast.AST, path: str, found: dict, docstrings: set) -> None:
    """The Hindi strings inside a function, a class or an expression, numbered in order."""
    strings = [c.value for c in ast.walk(node) if isinstance(c, ast.Constant) and isinstance(c.value, str)
               and DEVANAGARI.search(c.value) and id(c) not in docstrings]
    for i, text in enumerate(strings, 1):
        found[f"{path}#{i}"] = text


def digest(text: str) -> str:
    return hashlib.sha256(unicodedata.normalize("NFC", text).encode()).hexdigest()[:16]


def draft(name: str) -> bool:
    return name in DRAFTS or name.startswith(DRAFT_FUNCTIONS)


def test_every_hindi_line_is_as_the_user_reviewed_it_or_a_listed_draft():
    pinned, now = json.loads(PINS.read_text(encoding="utf-8")), hindi_lines()
    changed = {name: now[name] for name in now if not draft(name) and pinned.get(name) != digest(now[name])}
    assert not changed, ("Hindi changed since the user reviewed it, or is new and not listed in DRAFTS: re-review "
                         f"with the user, then refresh the pins (see this file's docstring): {changed}")
    assert not set(pinned) - set(now), f"pinned lines that are gone: {sorted(set(pinned) - set(now))}"


def test_the_drafts_are_real_lines():
    now = hindi_lines()
    assert DRAFTS <= set(now) and all(any(name.startswith(f) for name in now) for f in DRAFT_FUNCTIONS)


if __name__ == "__main__" and sys.argv[1:] == ["--pin"]:
    pins = {name: digest(text) for name, text in sorted(hindi_lines().items()) if not draft(name)}
    PINS.write_text(json.dumps(pins, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"pinned {len(pins)} reviewed Hindi lines in {PINS.name}")
