"""Tamper-evident, append-only logs: everything the agents, the fleet and the site did, kept to answer any claim.

Each line is one JSON record ending in ``seq`` (its position in the chain), ``prev`` (the previous line's hash) and
``hash`` = SHA-256 of ``prev`` followed by the line's own text up to the hash. Changing, removing or reordering a line
breaks every hash after it (``verify``). A file written before the chain existed is sealed by its first chained line:
its ``prev`` is the SHA-256 of every byte before it. The heads (last ``seq`` and ``hash`` of each file) are pushed to the
site (``audit_anchors`` in D1), so the history can also be checked against a copy kept outside this host.

One writer per file: every writer in this process shares the file's chain head (the fleet and the agent threads write
the same journal); two processes must never append to the same file.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
from pathlib import Path

GENESIS = "0" * 64
TAIL = re.compile(r', "seq": (\d+), "prev": "([0-9a-f]{64})", "hash": "([0-9a-f]{64})"\}$')
CHAIN_KEYS = ("seq", "prev", "hash")
_GUARD = threading.Lock()
_HEADS: dict[str, list] = {}   # resolved path -> [lock, next seq, last hash]; seq None until loaded from the file


def _digest(prev: str, body: str) -> str:
    return hashlib.sha256((prev + body).encode("utf-8")).hexdigest()


def _last_line(path: Path, chunk: int = 65536) -> str:
    """The last line of the file, read from its end (journals grow; the head is all a writer needs)."""
    with path.open("rb") as f:
        f.seek(0, 2)
        end = f.tell()
        buf = b""
        while end > 0:
            start = max(0, end - chunk)
            f.seek(start)
            buf = f.read(end - start) + buf
            end = start
            lines = buf.rstrip(b"\n").split(b"\n")
            if len(lines) > 1 or start == 0:
                return lines[-1].decode("utf-8", "replace")
    return ""


def head(path: Path) -> tuple[int, str] | None:
    """(seq, hash) of the file's last chained line, or None if it does not end with one."""
    try:
        m = TAIL.search(_last_line(path))
    except OSError:
        return None
    return (int(m.group(1)), m.group(3)) if m else None


def _load(path: Path) -> tuple[int, str]:
    if not path.exists() or path.stat().st_size == 0:
        return 0, GENESIS
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):   # a line cut by a crash: the next record starts on its own line
        with path.open("ab") as f:
            f.write(b"\n")
        raw += b"\n"
    h = head(path)
    if h:
        return h[0] + 1, h[1]
    # unchained history (written before the chain, or a cut line): sealed by the hash of all of it
    seq = 0
    for ln in reversed(raw.decode("utf-8", "replace").splitlines()):
        if m := TAIL.search(ln):
            seq = int(m.group(1)) + 1
            break
    return seq, hashlib.sha256(raw).hexdigest()


def append(path: Path, rec: dict) -> dict:
    """Appends ``rec`` as the next link of the file's chain and returns it with ``seq``, ``prev`` and ``hash``."""
    key = str(path.resolve())
    with _GUARD:
        h = _HEADS.setdefault(key, [threading.Lock(), None, None])
    with h[0]:
        if h[1] is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            h[1], h[2] = _load(path)
        body = json.dumps({**{k: v for k, v in rec.items() if k not in CHAIN_KEYS}, "seq": h[1], "prev": h[2]},
                          default=str, ensure_ascii=False)
        digest = _digest(h[2], body)
        with path.open("a", encoding="utf-8", newline="") as f:   # "\n" on every OS: the hashes cover exact bytes
            f.write(body[:-1] + f', "hash": "{digest}"}}\n')
        out = {**json.loads(body), "hash": digest}
        h[1], h[2] = h[1] + 1, digest
    return out


def forget(path: Path) -> None:
    """Drops the cached head (tests that rewrite a file in place)."""
    with _GUARD:
        _HEADS.pop(str(path.resolve()), None)


class AuditLog:
    """A chained JSONL file of records ``{"ts", "kind", ...}`` (timestamps in UTC, milliseconds)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def write(self, kind: str, **fields) -> dict:
        return append(self.path, {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
                                  "kind": kind, **fields})

    def read(self) -> list[dict]:
        return read(self.path)


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def verify(path: Path) -> dict:
    """Checks every link of the file. ``ok`` is False if any chained line was changed, removed or reordered.

    ``sealed``: chained lines whose ``prev`` is the hash of everything before them (the start of the chain on a file
    with older lines, or a restart after a cut line) instead of the previous line's hash."""
    raw = path.read_bytes() if path.exists() else b""
    problems: list[str] = []
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    offset, prev_hash, prev_seq, chained, sealed, legacy, loose = 0, None, None, 0, [], 0, []
    for n, b in enumerate(lines, 1):
        text = b.decode("utf-8", "replace")
        m = TAIL.search(text)
        if not m:
            if '"prev": "' in text and '"hash": "' in text:
                problems.append(f"line {n}: its chain fields were altered")
            elif prev_hash is not None:
                try:
                    json.loads(text)
                    problems.append(f"line {n}: a complete record outside the chain (added afterwards?)")
                except json.JSONDecodeError:
                    loose.append(n)    # a write cut by a crash: the next chained line must seal it
            elif chained == 0:
                legacy += 1            # written before the chain started
            prev_hash = None if prev_hash is None else "?"
            offset += len(b) + 1
            continue
        seq, prev, h = int(m.group(1)), m.group(2), m.group(3)
        body = text[: text.rindex(', "hash": "')] + "}"
        if _digest(prev, body) != h:
            problems.append(f"line {n}: content does not match its hash (changed after it was written)")
        if prev_hash not in (None, "?") and prev == prev_hash:
            pass
        elif prev == hashlib.sha256(raw[:offset]).hexdigest() or (offset == 0 and prev == GENESIS):
            if offset:
                sealed.append(n)
        else:
            problems.append(f"line {n}: does not follow the line before it (a line was removed, changed or moved)")
        if prev_seq is not None and seq != prev_seq + 1:
            problems.append(f"line {n}: sequence {seq} after {prev_seq}")
        prev_hash, prev_seq, chained = h, seq, chained + 1
        offset += len(b) + 1
    return {"path": str(path), "lines": len(lines), "chained": chained, "legacy": legacy, "loose": loose,
            "sealed": sealed, "head": head(path) if chained else None, "ok": not problems, "problems": problems}


def files(runs_root: Path) -> list[Path]:
    """Every audit file under the runs root: agents' journals, account fills and readings, the site's actions."""
    root = Path(runs_root)
    out = [p for name in ("journal.jsonl", "fills.jsonl", "account.jsonl") for p in root.glob(f"*/{name}")]
    return sorted(out + list(root.glob("web-audit-*.jsonl")))


def heads(paths: list[Path], root: Path) -> dict[str, list]:
    """{file relative to the runs root: [seq, hash]} of every chained file (what the site keeps as anchors)."""
    out = {}
    for p in paths:
        h = head(p)
        if h:
            out[p.relative_to(root).as_posix()] = [h[0], h[1]]
    return out
