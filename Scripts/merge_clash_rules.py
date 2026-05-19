#!/usr/bin/env python3
"""Merge and audit Clash rule lists.

Designed for GitHub Actions in this repository. It keeps output paths compatible
while adding deterministic de-duplication, basic normalization, shadow detection,
conflict reporting, and optional low-memory pruning.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, ipaddress, json, os, re, sys, urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

RULE_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6", "GEOIP", "SRC-IP-CIDR", "PROCESS-NAME", "MATCH"}
DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX"}
SECRET_RE = re.compile(r"(?i)(token|secret|password|passwd|pwd|key|api[_-]?key)=([^&\s]+)")
URL_QUERY_RE = re.compile(r"(https?://[^?\s]+)\?[^\s]+")

@dataclass(frozen=True)
class Rule:
    raw: str
    typ: str
    value: str
    options: tuple[str, ...]
    source: str
    line: int

    @property
    def key(self) -> tuple[str, str]:
        return (self.typ, self.value.lower())

    def out(self) -> str:
        parts = [self.typ, self.value, *self.options]
        return ",".join(parts)


def redact(s: str) -> str:
    return SECRET_RE.sub(r"\1=REDACTED", URL_QUERY_RE.sub(r"\1?REDACTED_QUERY", s))


def read_source(src: str) -> str:
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src, headers={"User-Agent": "ReidVin-rule-merge/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", "ignore")
    return Path(src).read_text(encoding="utf-8", errors="ignore")


def normalize_line(line: str) -> str | None:
    s = line.strip().lstrip("-").strip()
    if not s or s.startswith(("#", "//", ";")):
        return None
    # strip inline comments only when separated by whitespace
    s = re.sub(r"\s+#.*$", "", s).strip()
    if not s:
        return None
    if s.startswith("+."):
        s = s[2:]
    if s.startswith("||"):
        s = s[2:]
    if s.startswith("."):
        s = s[1:]
    parts = [p.strip() for p in s.split(",")]
    if not parts:
        return None
    typ = parts[0].upper()
    if typ not in RULE_TYPES:
        # Accept bare domains from simple domain lists. Require a plausible TLD
        # with at least two letters to avoid turning arbitrary text into rules.
        if re.match(r"^(?:[a-zA-Z0-9_-]+\.)+[a-zA-Z]{2,}$", s):
            return f"DOMAIN-SUFFIX,{s.lower()}"
        return None
    if typ == "MATCH":
        return "MATCH"
    if len(parts) < 2 or not parts[1]:
        return None
    val = parts[1].strip().strip(".").lower() if typ in DOMAIN_TYPES | {"DOMAIN-KEYWORD"} else parts[1].strip()
    if typ in {"IP-CIDR", "IP-CIDR6", "SRC-IP-CIDR"}:
        try:
            val = str(ipaddress.ip_network(val, strict=False))
        except Exception:
            return None
    opts = [p for p in parts[2:] if p]
    return ",".join([typ, val, *opts])


def parse_rules(text: str, source: str) -> list[Rule]:
    rules: list[Rule] = []
    for idx, line in enumerate(text.splitlines(), 1):
        norm = normalize_line(line)
        if not norm:
            continue
        parts = [p.strip() for p in norm.split(")")]
        parts = [p.strip() for p in norm.split(",")]
        typ = parts[0]
        val = parts[1] if len(parts) > 1 else ""
        opts = tuple(parts[2:])
        rules.append(Rule(norm, typ, val, opts, source, idx))
    return rules


def domain_parent(child: str, parent: str) -> bool:
    c = child.lower().strip(".")
    p = parent.lower().strip(".")
    return c != p and c.endswith("." + p)


def prune_shadowed(rules: list[Rule]) -> tuple[list[Rule], list[dict]]:
    suffixes: list[Rule] = []
    keep: list[Rule] = []
    shadows: list[dict] = []
    for r in rules:
        shadow_by = None
        if r.typ in DOMAIN_TYPES:
            for p in suffixes:
                if p.options == r.options and (r.value == p.value or domain_parent(r.value, p.value)):
                    shadow_by = p
                    break
        if shadow_by:
            shadows.append({"rule": r.out(), "source": redact(r.source), "line": r.line, "shadowed_by": shadow_by.out(), "shadow_source": redact(shadow_by.source)})
            continue
        keep.append(r)
        if r.typ == "DOMAIN-SUFFIX":
            suffixes.append(r)
    return keep, shadows


def load_sources(args: argparse.Namespace) -> list[str]:
    srcs: list[str] = []
    for s in args.source or []:
        srcs.append(s)
    if args.sources_file:
        srcs += [l.strip() for l in Path(args.sources_file).read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]
    env = os.environ.get(args.sources_env or "") if args.sources_env else ""
    if env:
        srcs += [l.strip() for l in env.splitlines() if l.strip()]
    # preserve order, unique source URLs
    seen=set(); out=[]
    for s in srcs:
        if s not in seen:
            seen.add(s); out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append")
    ap.add_argument("--sources-file")
    ap.add_argument("--sources-env")
    ap.add_argument("--output", required=True)
    ap.add_argument("--title", default="# Clash merged rules")
    ap.add_argument("--description", default="")
    ap.add_argument("--author", default="# 作者：Reid_Vin_Action")
    ap.add_argument("--analysis-dir", default="analysis")
    ap.add_argument("--low-memory", action="store_true", help="drop rules shadowed by previous parent rules")
    ap.add_argument("--fail-on-empty", action="store_true")
    args = ap.parse_args()

    sources = load_sources(args)
    all_rules: list[Rule] = []
    source_stats=[]
    for src in sources:
        try:
            text = read_source(src)
            parsed = parse_rules(text, src)
            all_rules.extend(parsed)
            source_stats.append({"source": redact(src), "rules": len(parsed), "ok": True})
        except Exception as e:
            source_stats.append({"source": redact(src), "rules": 0, "ok": False, "error": repr(e)})
            print(f"WARN failed source {redact(src)}: {e}", file=sys.stderr)

    seen: dict[tuple[str,str,tuple[str,...]], Rule] = {}
    dup=[]
    deduped=[]
    key_to_sources: dict[tuple[str,str], set[str]] = {}
    for r in all_rules:
        full = (r.typ, r.value.lower(), r.options)
        key_to_sources.setdefault(r.key,set()).add(redact(r.source))
        if full in seen:
            dup.append({"rule": r.out(), "source": redact(r.source), "line": r.line, "first_source": redact(seen[full].source), "first_line": seen[full].line})
            continue
        seen[full]=r; deduped.append(r)

    final = deduped
    shadows=[]
    if args.low_memory:
        final, shadows = prune_shadowed(deduped)
    else:
        _, shadows = prune_shadowed(deduped)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.fail_on_empty and not final:
        raise SystemExit("no rules generated")
    update_time = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    header = [
        args.title,
        args.description or "# Generated by Scripts/merge_clash_rules.py",
        "# 基于以下分流规则合并：",
        *["# " + redact(s) for s in sources],
        f"# 更新时间：{update_time}",
        f"# 原始规则数：{len(all_rules)}条",
        f"# 去重后规则数：{len(deduped)}条",
        f"# 输出规则数：{len(final)}条",
        f"# 重复规则数：{len(dup)}条",
        f"# 遮蔽规则数：{len(shadows)}条",
        args.author,
        "",
    ]
    out_path.write_text("\n".join(header + [r.out() for r in final]) + "\n", encoding="utf-8")

    analysis = Path(args.analysis_dir); analysis.mkdir(parents=True, exist_ok=True)
    stem = out_path.stem
    summary = {"output": str(out_path), "sources": source_stats, "raw_rules": len(all_rules), "deduped_rules": len(deduped), "output_rules": len(final), "duplicates": len(dup), "shadowed": len(shadows), "low_memory": args.low_memory}
    (analysis / f"{stem}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, rows, fields in [
        ("duplicates", dup, ["rule","source","line","first_source","first_line"]),
        ("shadowed", shadows, ["rule","source","line","shadowed_by","shadow_source"]),
    ]:
        with (analysis / f"{stem}.{name}.tsv").open("w", encoding="utf-8", newline="") as f:
            w=csv.DictWriter(f, fieldnames=fields, delimiter="\t"); w.writeheader(); w.writerows(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
