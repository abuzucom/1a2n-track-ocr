#!/usr/bin/env python3
"""Warn on common British English spelling variants.

AGENTS.md style rule: use American spelling in code, comments, commit
messages, and documentation. This is a warning-only check: it always
exits 0, per the policy's own stated scope for this script. It uses a
curated word list rather than generic suffix matching (-our, -ise,
-re) because those suffixes also appear in ordinary American words
("your", "hour", "genre", "acre"), which would make a suffix-based
version noisy to the point of being ignored.
"""

from __future__ import annotations

import re
import subprocess
import sys

SELF_PATH_SUFFIX = "check_us_spelling.py"

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".exe", ".dll",
}

BRITISH_TO_AMERICAN = {
    "colour": "color", "colours": "colors", "coloured": "colored", "colouring": "coloring",
    "favour": "favor", "favours": "favors", "favoured": "favored", "favouring": "favoring",
    "behaviour": "behavior", "behaviours": "behaviors",
    "honour": "honor", "honours": "honors", "honoured": "honored",
    "neighbour": "neighbor", "neighbours": "neighbors", "neighbouring": "neighboring",
    "labour": "labor", "labours": "labors", "laboured": "labored", "labouring": "laboring",
    "rumour": "rumor", "rumours": "rumors",
    "humour": "humor", "humoured": "humored", "humouring": "humoring",
    "flavour": "flavor", "flavours": "flavors", "flavoured": "flavored",
    "initialise": "initialize", "initialised": "initialized", "initialising": "initializing",
    "initialisation": "initialization",
    "organise": "organize", "organised": "organized", "organising": "organizing",
    "organisation": "organization", "organisations": "organizations",
    "realise": "realize", "realised": "realized", "realising": "realizing",
    "realisation": "realization",
    "recognise": "recognize", "recognised": "recognized", "recognising": "recognizing",
    "analyse": "analyze", "analysed": "analyzed", "analysing": "analyzing",
    "catalogue": "catalog", "catalogued": "cataloged",
    "dialogue": "dialog",
    "centre": "center", "centres": "centers", "centred": "centered", "centring": "centering",
    "theatre": "theater", "theatres": "theaters",
    "litre": "liter", "litres": "liters",
    "fibre": "fiber", "fibres": "fibers",
    "calibre": "caliber",
    "travelling": "traveling", "travelled": "traveled", "traveller": "traveler",
    "cancelled": "canceled", "cancelling": "canceling",
    "modelling": "modeling", "modelled": "modeled",
    "labelled": "labeled", "labelling": "labeling",
    "signalling": "signaling", "signalled": "signaled",
    "jewellery": "jewelry",
    "whilst": "while",
    "amongst": "among",
    "defence": "defense",
    "licence": "license",
    "programme": "program",
}

WORD_RE = re.compile(r"\b[A-Za-z]+\b")


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tracked_files() -> list[str]:
    output = run_git(["ls-files"])
    return [line for line in output.splitlines() if line]


def is_binary_path(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in BINARY_EXTENSIONS)


def scan_file(path: str) -> list[str]:
    warnings = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except OSError:
        return warnings

    for lineno, line in enumerate(lines, start=1):
        for word in WORD_RE.findall(line):
            suggestion = BRITISH_TO_AMERICAN.get(word.lower())
            if suggestion:
                warnings.append(f"{path}:{lineno}: '{word}' -> prefer American spelling '{suggestion}'")
    return warnings


def main() -> int:
    warnings = []
    for path in tracked_files():
        if path.endswith(SELF_PATH_SUFFIX) or is_binary_path(path):
            continue
        warnings.extend(scan_file(path))

    if warnings:
        print("US spelling check (warning only):")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("US spelling check passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
