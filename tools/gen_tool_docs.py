#!/usr/bin/env python3
"""Rewrite the generated tool table in CLAUDE.md and docs/tools.md from agent/tools.py.  Usage: python tools/gen_tool_docs.py"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from agent.tool_docs import END, START, render_markdown   # noqa: E402


TARGETS = ("CLAUDE.md", os.path.join("docs", "tools.md"))


def main():
    for name in TARGETS:
        path = os.path.join(ROOT, name)
        text = open(path).read()
        i, j = text.index(START), text.index(END) + len(END)
        open(path, "w").write(text[:i] + render_markdown() + text[j:])


if __name__ == "__main__":
    main()
