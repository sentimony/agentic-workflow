#!/usr/bin/env python3
"""Print the context digest of a record host (plan or spec).

The digest binds a Verify verdict to the requirements context: the host text
without its record section, the spec named by a plan's `Spec:` header, and the
`Ruling:` / `Deferred:` lines of every record section. Exit 2 with empty stdout
on any ambiguity (fail-closed); see ../context-digest.md.
"""
import hashlib
import os
import re
import sys

RECORD_HEADINGS = ("## Execution record", "## Verification record")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
SPEC_LINE = re.compile(r"^\**Spec:\**\s*(.+?)\s*$")
# Rulings written by verify itself and by the finalize gate must not invalidate a PASS.
EXCLUDED_RULINGS = ("Ruling: round ", "Ruling: no review")


class DigestError(Exception):
    pass


def read_text(path):
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DigestError("cannot read %s: %s" % (path, exc))
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_host(text, label):
    """Return (body lines, record lines) with fence-aware section boundaries."""
    body, record = [], []
    fence = None  # (char, length) while inside a fenced block
    in_record = False
    seen = {}
    for line in text.split("\n"):
        m = FENCE.match(line)
        if fence is None:
            if m:
                marker = m.group(1)
                fence = (marker[0], len(marker))
            elif line.startswith("## "):
                heading = line.rstrip()
                if heading in RECORD_HEADINGS:
                    seen[heading] = seen.get(heading, 0) + 1
                    if seen[heading] > 1:
                        raise DigestError("%s: duplicate heading %r" % (label, heading))
                    in_record = True
                    continue
                in_record = False
        else:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2).strip():
                fence = None
        (record if in_record else body).append(line)
    if fence is not None:
        raise DigestError("%s: unclosed fenced block" % label)
    return body, record


def record_lines(record):
    out = []
    for line in record:
        if line.startswith("Deferred:"):
            out.append(line)
        elif line.startswith("Ruling:") and not line.startswith(EXCLUDED_RULINGS):
            out.append(line)
    return out


def repo_root(start):
    cur = os.path.dirname(os.path.abspath(start))
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.dirname(os.path.abspath(start))
        cur = parent


def spec_path(body, host):
    fence = None
    for line in body:
        m = FENCE.match(line)
        if fence is None:
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
                continue
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                and not m.group(2).strip():
            fence = None
            continue
        if fence is not None:
            continue
        s = SPEC_LINE.match(line)
        if s:
            value = s.group(1).strip("` ")
            if value.lower() == "none" or not value:
                return None
            if os.path.isabs(value):
                return value
            return os.path.join(repo_root(host), value)
    return None


def canonical(host):
    text = read_text(host)
    body, record = split_host(text, host)
    parts = [("host", "\n".join(body)), ("host-rulings", "\n".join(record_lines(record)))]
    spec = spec_path(body, host)
    if spec is not None:
        sbody, srecord = split_host(read_text(spec), spec)
        parts.append(("spec", "\n".join(sbody)))
        parts.append(("spec-rulings", "\n".join(record_lines(srecord))))
    return b"".join(b"\0" + name.encode() + b"\0" + data.encode("utf-8") for name, data in parts)


def digest(host):
    return "sha256:" + hashlib.sha256(canonical(host)).hexdigest()


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: context_digest.py <host-path>\n")
        return 2
    try:
        value = digest(argv[1])
    except DigestError as exc:
        sys.stderr.write("context digest failed: %s\n" % exc)
        return 2
    sys.stdout.write(value + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
