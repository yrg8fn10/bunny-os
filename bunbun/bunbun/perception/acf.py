"""Minimal Valve KeyValues (VDF / ACF) reader.

Steam's manifests are not JSON and not INI: they are nested quoted tokens.
This parser handles the subset Steam actually emits, including ``//`` comments,
unquoted tokens, and escaped quotes.  It is read-only by design.
"""
from __future__ import annotations

from typing import Any, Iterator

TOKEN_SPECIAL = '{}"'


class ParseError(ValueError):
    pass


def _tokens(text: str) -> Iterator[str]:
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch in "{}":
            yield ch
            i += 1
            continue
        if ch == '"':
            i += 1
            buf: list[str] = []
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    break
                buf.append(c)
                i += 1
            else:
                raise ParseError("unterminated string")
            yield "".join(buf)
            continue
        start = i
        while i < n and text[i] not in ' \t\r\n{}"':
            i += 1
        yield text[start:i]


def parse(text: str) -> dict[str, Any]:
    """Parse KeyValues text into a nested dict, preserving key order."""
    tokens = list(_tokens(text))
    pos = 0

    def block() -> dict[str, Any]:
        nonlocal pos
        result: dict[str, Any] = {}
        while pos < len(tokens):
            key = tokens[pos]
            if key == "}":
                pos += 1
                return result
            if key == "{":
                raise ParseError("unexpected '{'")
            pos += 1
            if pos >= len(tokens):
                result[key] = ""
                break
            value = tokens[pos]
            if value == "{":
                pos += 1
                result[key] = block()
            elif value == "}":
                result[key] = ""
                pos += 1
                return result
            else:
                result[key] = value
                pos += 1
        return result

    parsed = block()
    if pos < len(tokens):
        raise ParseError("trailing tokens after root block")
    return parsed


def parse_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse(fh.read())
