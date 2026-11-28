#!/usr/bin/env python3
"""Parse a uiautomator dump out of an adbrun round output file (or a standalone .xml) and list
the tappable/visible nodes with tap centers. password="true" node text is REDACTED (bullet count only).

usage: uidump.py <round.out | ui.xml> [filter-substring]
"""
import re
import sys
import xml.etree.ElementTree as ET

NODE_RE = re.compile(r'<node [^>]*?/>')


def main():
    path = sys.argv[1]
    flt = sys.argv[2] if len(sys.argv) > 2 else None
    raw = open(path, encoding="utf-8", errors="replace").read()
    start = raw.find("<?xml")
    if start >= 0:
        end = raw.find("</hierarchy>", start)
        raw = raw[start:end + len("</hierarchy>")] if end > start else raw[start:]
    try:
        root = ET.fromstring(raw.encode("utf-8"))
    except ET.ParseError as exc:
        print("PARSE-FAIL %s (len=%d) head=%r" % (exc, len(raw), raw[:120]))
        return 2
    n = 0
    for node in root.iter("node"):
        text = node.get("text") or ""
        rid = node.get("resource-id") or ""
        desc = node.get("content-desc") or ""
        b = node.get("bounds") or ""
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
        cx = cy = ""
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            if x2 > x1 and y2 > y1:
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        pwd = node.get("password") == "true"
        if pwd:
            shown = "<password len=%d>" % len(text)
        else:
            shown = text
        label = " | ".join(x for x in (shown, desc, rid.split("/")[-1]) if x)
        if not label:
            continue
        cls = (node.get("class") or "").split(".")[-1]
        clickable = "C" if node.get("clickable") == "true" else "-"
        line = "%-14s %s (%s,%s) %s" % (cls, b, cx, cy, label[:110])
        if flt and flt.lower() not in line.lower():
            continue
        print(line)
        n += 1
    print("-- %d labelled nodes" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
