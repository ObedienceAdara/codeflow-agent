#!/usr/bin/env python3
"""Delete all __pycache__ directories recursively."""
import os
import shutil
from pathlib import Path

root = Path(__file__).parent
deleted = 0

for p in root.rglob("__pycache__"):
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
        deleted += 1
        print(f"  deleted: {p}")

print(f"[clean] Removed {deleted} __pycache__ folder(s).")
