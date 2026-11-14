#!/usr/bin/env python3
"""Read-only record checks shared by verify and finalize (see ../record-gate.md).

  record_gate.py --blockers <host>
  record_gate.py --gate <host> --tree <fingerprint> --context <digest>
                 [--integrate merge|squash|pr]

Exit codes: 0 ok / no blockers, 1 refused / blockers, 2 error (stdout empty).
The script writes nothing and calls neither git nor the network.
"""
import argparse
import json
import re
import sys

SECTIONS = ("## Execution record", "## Verification record")
FENCE_TEXT = re.compile(r"^```text\s*$")
FENCE_END = re.compile(r"^```\s*$")
VERIFY = re.compile(
    r"^Verify: (PASS|FAIL|INCOMPLETE|BLOCKED) (full|compact) tree ([0-9a-f]{40}|[0-9a-f]{64}) "
    r"(?:context (sha256:[0-9a-f]{64}|none) )?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})"
    r"(?: (working|scoped .+))?$")
REVIEW = re.compile(r"^Review R(\d+): .*\bmode (code|document|re-review)\s*$")
FINDING = re.compile(r"^Finding (R\d+-F\d+): (Critical|Important|Minor)\b")
RECEIVED = re.compile(r"^Received R(\d+): (.*)$")
DISPOSITION = re.compile(r"\b((?:R\d+-)?F\d+) (ACCEPT|REJECT|PARTIAL|DEFER|ESCALATE|OUTDATED)\b")
RE_REVIEW = re.compile(r"Re-review: (not needed|needed)\s*$")
ESCALATION = re.compile(r"^Ruling: (R\d+-F\d+) escalation decided - ")
MARKERS = ("Ruling: plan revised after spec re-approval - ", "Ruling: spec re-approved - ")
CLOSING = ("REJECT", "OUTDATED", "DEFER", "ACCEPT", "PARTIAL")

# Fixed refusal codes; record-gate.md carries the same table (checked by the tests).
REASON_CODES = (
    "no-verify", "verify-not-pass", "verify-compact", "verify-working", "verify-scoped",
    "tree-mismatch", "context-missing", "context-mismatch", "no-code-review",
    "re-review-needed", "open-blocker:<id>",
)


class GateError(Exception):
    pass


def read_record(path):
    """Return (lines inside the record's text blocks, kind of record host)."""
    try:
        with open(path, "rb") as handle:
            text = handle.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateError("cannot read %s: %s" % (path, exc))
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Fence-aware: a heading inside a fenced block is no section boundary.
    fence = None
    found, current, out = {}, None, []
    for line in lines:
        if fence is None:
            m = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
            elif line.startswith("## "):
                heading = line.rstrip()
                current = None
                if heading in SECTIONS:
                    found[heading] = found.get(heading, 0) + 1
                    if sum(found.values()) > 1:
                        raise GateError("more than one record section")
                    current = heading
        else:
            m = re.match(r"^ {0,3}(`{3,}|~{3,})\s*$", line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fence = None
        if current is not None:
            out.append(line)
    if not found:
        return [], None
    kind = "plan" if "## Execution record" in found else "spec"
    return text_block_lines(out), kind


def text_block_lines(section):
    lines, inside = [], False
    for line in section:
        if not inside:
            if FENCE_TEXT.match(line):
                inside = True
        elif FENCE_END.match(line):
            inside = False
        else:
            lines.append(line)
    return lines


def parse(lines):
    """Turn record lines into a list of (kind, data) events in file order."""
    events = []
    for line in lines:
        if line.startswith("Verify:"):
            m = VERIFY.match(line)
            if not m:
                raise GateError("unparseable Verify line: %r" % line)
            events.append(("verify", {
                "verdict": m.group(1), "mode": m.group(2), "tree": m.group(3),
                "context": m.group(4), "suffix": m.group(6) or ""}))
        elif line.startswith("Review R"):
            m = REVIEW.match(line)
            if not m:
                raise GateError("unparseable Review line: %r" % line)
            events.append(("review", {"mode": m.group(2)}))
        elif line.startswith("Finding "):
            m = FINDING.match(line)
            if not m:
                raise GateError("unparseable Finding line: %r" % line)
            events.append(("finding", {"id": m.group(1), "severity": m.group(2)}))
        elif line.startswith("Received R"):
            m = RECEIVED.match(line)
            if not m:
                raise GateError("unparseable Received line: %r" % line)
            rnd = "R" + m.group(1)
            disp = []
            for ident, word in DISPOSITION.findall(m.group(2)):
                disp.append((ident if ident.startswith("R") else "%s-%s" % (rnd, ident), word))
            rr = RE_REVIEW.search(m.group(2))
            events.append(("received", {"dispositions": disp,
                                        "rereview": bool(rr and rr.group(1) == "needed")}))
        elif line.startswith("Ruling:"):
            events.append(("ruling", {"text": line}))
        elif line.startswith("Base:"):
            events.append(("base", {}))
    return events


def blockers(events, require_verified=False):
    """Open blockers. With require_verified, ACCEPT/PARTIAL close only before a later PASS."""
    findings, last = {}, {}
    for i, (kind, data) in enumerate(events):
        if kind == "finding":
            findings[data["id"]] = data["severity"]
        elif kind == "received":
            for ident, word in data["dispositions"]:
                last[ident] = (word, i)
    out = []
    ids = list(findings) + [k for k in last if k not in findings]
    for ident in ids:
        severity = findings.get(ident, "Important")
        word, at = last.get(ident, (None, -1))
        if word == "ESCALATE":
            decided = any(k == "ruling" and ESCALATION.match(d["text"])
                          and ESCALATION.match(d["text"]).group(1) == ident
                          for k, d in events[at + 1:])
            if not decided:
                out.append({"id": ident, "severity": severity,
                            "why": "ESCALATE without an escalation decided ruling"})
            continue
        if severity not in ("Critical", "Important"):
            continue
        if word is None:
            out.append({"id": ident, "severity": severity, "why": "no Received disposition"})
        elif require_verified and word in ("ACCEPT", "PARTIAL"):
            passed = any(k == "verify" and d["verdict"] == "PASS" and d["mode"] == "full"
                         and not d["suffix"] for k, d in events[at + 1:])
            if not passed:
                out.append({"id": ident, "severity": severity,
                            "why": "%s not proven by a later full Verify PASS" % word})
    return out


def has_code_review(events, kind):
    """A code review (a re-review follows one, so it adds nothing) after the cut."""
    cut = 0
    for i, (k, d) in enumerate(events):
        if k == "ruling" and d["text"].startswith(MARKERS):
            cut = i + 1
    if cut == 0 and kind == "plan":
        for i, (k, d) in enumerate(events):
            if k == "base":
                cut = i + 1
    for k, d in events[cut:]:
        if k == "review" and d["mode"] == "code":
            return True
        if k == "ruling" and d["text"].startswith("Ruling: no review - "):
            return True
    return False


def gate(events, kind, tree, context, integrate):
    verifies = [d for k, d in events if k == "verify"]
    if not verifies:
        return ["no-verify"]
    v, reasons = verifies[-1], []
    if v["verdict"] != "PASS":
        reasons.append("verify-not-pass")
    if v["mode"] == "compact":
        reasons.append("verify-compact")
    if v["suffix"] == "working":
        reasons.append("verify-working")
    elif v["suffix"].startswith("scoped"):
        reasons.append("verify-scoped")
    if v["tree"] != tree:
        reasons.append("tree-mismatch")
    if v["context"] is None:
        reasons.append("context-missing")
    elif v["context"] != context:
        reasons.append("context-mismatch")
    if integrate in ("merge", "squash") and not has_code_review(events, kind):
        reasons.append("no-code-review")
    for b in blockers(events, require_verified=True):
        reasons.append("open-blocker:" + b["id"])
    last_received = None
    for i, (k, d) in enumerate(events):
        if k == "received":
            last_received = (i, d)
    if last_received and last_received[1]["rereview"] and not any(
            k == "review" for k, _ in events[last_received[0] + 1:]):
        reasons.append("re-review-needed")
    return reasons


def main(argv):
    ap = argparse.ArgumentParser(prog="record_gate.py")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--blockers", metavar="HOST")
    mode.add_argument("--gate", metavar="HOST")
    ap.add_argument("--tree")
    ap.add_argument("--context")
    ap.add_argument("--integrate", choices=("merge", "squash", "pr"), default="merge")
    try:
        args = ap.parse_args(argv[1:])
    except SystemExit:
        return 2
    try:
        if args.blockers:
            lines, kind = read_record(args.blockers)
            found = blockers(parse(lines))
            print(json.dumps({"blockers": found}))
            return 1 if found else 0
        if args.tree is None or args.context is None:
            sys.stderr.write("--gate needs --tree and --context\n")
            return 2
        lines, kind = read_record(args.gate)
        reasons = gate(parse(lines), kind, args.tree, args.context, args.integrate)
        print(json.dumps({"ok": not reasons, "reasons": reasons}))
        return 0 if not reasons else 1
    except GateError as exc:
        sys.stderr.write("record gate failed: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
