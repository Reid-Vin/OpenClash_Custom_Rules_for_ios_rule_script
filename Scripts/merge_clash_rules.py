#!/usr/bin/env python3
"""Merge and audit Clash rule lists with YAML governance and lightweight processors."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import ipaddress
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

RULE_TYPES = {
    "DOMAIN",
    "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD",
    "IP-CIDR",
    "IP-CIDR6",
    "GEOIP",
    "SRC-IP-CIDR",
    "PROCESS-NAME",
    "MATCH",
}
DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX"}
SECRET_RE = re.compile(r"(?i)(token|secret|password|passwd|pwd|key|api[_-]?key)=([^&\s]+)")
URL_QUERY_RE = re.compile(r"(https?://[^?\s]+)\?[^\s]+")
CIDR_V4_RE = re.compile(r"^[0-9]{1,3}(?:\.[0-9]{1,3}){3}/[0-9]{1,2}$")
CIDR_V6_RE = re.compile(r"^[0-9a-fA-F:]+/[0-9]{1,3}$")
IP_V4_RE = re.compile(r"^[0-9]{1,3}(?:\.[0-9]{1,3}){3}$")


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
        return ",".join([self.typ, self.value, *self.options])


@dataclass(frozen=True)
class RoutedRule:
    rule: str
    target: str


def redact(s: str) -> str:
    return SECRET_RE.sub(r"\1=REDACTED", URL_QUERY_RE.sub(r"\1?REDACTED_QUERY", s))


def read_source(src: str) -> str:
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src, headers={"User-Agent": "ReidVin-rule-merge/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", "ignore")
    return Path(src).read_text(encoding="utf-8", errors="ignore")


def normalize_line(line: str) -> str | None:
    s = str(line).strip().lstrip("-").strip()
    if not s or s.startswith(("#", "//", ";")):
        return None
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
        parts = [p.strip() for p in norm.split(",")]
        rules.append(Rule(norm, parts[0], parts[1] if len(parts) > 1 else "", tuple(parts[2:]), source, idx))
    return rules


def parse_rule_items(items: list[str], source: str) -> list[Rule]:
    rules: list[Rule] = []
    for idx, item in enumerate(items, 1):
        norm = normalize_line(item)
        if not norm:
            continue
        parts = [p.strip() for p in norm.split(",")]
        rules.append(Rule(norm, parts[0], parts[1] if len(parts) > 1 else "", tuple(parts[2:]), source, idx))
    return rules


def parse_routes(data: dict) -> list[RoutedRule]:
    routed: list[RoutedRule] = []
    sections = data.get("ROUTES") or data.get("routes") or []
    if isinstance(sections, dict):
        sections = [sections]
    for section in sections:
        if not isinstance(section, dict):
            continue
        target = str(section.get("TO") or section.get("to") or "").strip()
        if not target:
            continue
        rules = section.get("RULES") or section.get("rules") or []
        for item in rules:
            norm = normalize_line(item)
            if norm:
                routed.append(RoutedRule(rule=norm, target=target))
    return routed


def load_governance(path: str | None, current_group: str | None) -> dict:
    base = {"prepend_rules": [], "append_rules": [], "drop_rules": [], "routed_rules": []}
    if not path:
        return base

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return base

    base["routed_rules"] = parse_routes(data)

    groups = data.get("groups") or {}
    if current_group and isinstance(groups, dict):
        section = groups.get(current_group) or {}
        if isinstance(section, dict):
            base["prepend_rules"] = [normalize_line(x) for x in section.get("prepend_rules", []) if normalize_line(x)]
            base["append_rules"] = [normalize_line(x) for x in section.get("append_rules", []) if normalize_line(x)]
            base["drop_rules"] = [normalize_line(x) for x in section.get("drop_rules", []) if normalize_line(x)]
    return base


def resolve_routed_rules(current_group: str | None, routed_rules: list[RoutedRule]) -> tuple[list[str], set[str]]:
    if not current_group:
        return [], set()
    prepend: list[str] = []
    governed_all: set[str] = set()
    for item in routed_rules:
        governed_all.add(item.rule)
        if item.target == current_group:
            prepend.append(item.rule)
    drop = {rule for rule in governed_all if rule not in set(prepend)}
    return prepend, drop


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
            shadows.append({
                "rule": r.out(),
                "source": redact(r.source),
                "line": r.line,
                "shadowed_by": shadow_by.out(),
                "shadow_source": redact(shadow_by.source),
            })
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
        srcs += [
            l.strip()
            for l in Path(args.sources_file).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
    env = os.environ.get(args.sources_env or "") if args.sources_env else ""
    if env:
        srcs += [l.strip() for l in env.splitlines() if l.strip()]
    seen = set()
    out = []
    for s in srcs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def process_switchyomega_whitelist(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith(";") or s.startswith("["):
            continue
        if ":" in s or re.match(r"^([0-9*]{1,3}\.){3}[0-9*]{1,3}$", s):
            continue
        s = re.sub(r"^\*\.", "", s)
        s = re.sub(r"^\.", "", s)
        if not s or "*" in s:
            continue
        out.append(f"DOMAIN-SUFFIX,{s}")
    return out


def process_gfw_text(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("!") or s.startswith("[") or s.startswith("@@"):
            continue
        if CIDR_V4_RE.match(s):
            out.append(f"IP-CIDR,{s},no-resolve")
            continue
        if CIDR_V6_RE.match(s):
            out.append(f"IP-CIDR6,{s},no-resolve")
            continue
        s = re.sub(r"^\|\|", "", s)
        s = re.sub(r"^\|https?://", "", s)
        s = re.sub(r"^https?://", "", s)
        s = re.sub(r"^\.", "", s)
        if "*" in s:
            continue
        s = re.split(r"[:/]", s, maxsplit=1)[0].strip()
        if not s:
            continue
        if IP_V4_RE.match(s):
            out.append(f"DOMAIN,{s}")
        else:
            out.append(f"DOMAIN-SUFFIX,{s}")
    return out


def build_rules_from_processor(processor: str, source_texts: list[tuple[str, str]]) -> tuple[list[Rule], list[dict]]:
    if processor == "merge":
        rules: list[Rule] = []
        stats: list[dict] = []
        for src, text in source_texts:
            parsed = parse_rules(text, src)
            rules.extend(parsed)
            stats.append({"source": redact(src), "rules": len(parsed), "ok": True})
        return rules, stats

    if processor == "switchyomega_domain":
        if len(source_texts) != 1:
            raise SystemExit("switchyomega_domain processor requires exactly 1 source")
        src, text = source_texts[0]
        items = process_switchyomega_whitelist(text)
        return parse_rule_items(items, src), [{"source": redact(src), "rules": len(items), "ok": True}]

    if processor == "gfw_ultimate":
        if len(source_texts) < 2:
            raise SystemExit("gfw_ultimate processor requires at least 2 sources")
        rules: list[Rule] = []
        stats: list[dict] = []
        first_src, first_text = source_texts[0]
        first_items = process_gfw_text(first_text)
        rules.extend(parse_rule_items(first_items, first_src))
        stats.append({"source": redact(first_src), "rules": len(first_items), "ok": True})
        for src, text in source_texts[1:]:
            parsed = [r for r in parse_rules(text, src) if r.typ.startswith("DOMAIN") or r.typ.startswith("IP-CIDR")]
            rules.extend(parsed)
            stats.append({"source": redact(src), "rules": len(parsed), "ok": True})
        return rules, stats

    if processor == "china_max_ip":
        rules: list[Rule] = []
        stats: list[dict] = []
        for src, text in source_texts:
            parsed = [r for r in parse_rules(text, src) if r.typ in {"IP-CIDR", "IP-CIDR6"}]
            rules.extend(parsed)
            stats.append({"source": redact(src), "rules": len(parsed), "ok": True})
        return rules, stats

    raise SystemExit(f"Unknown processor: {processor}")


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
    ap.add_argument("--governance-file", help="YAML governance file")
    ap.add_argument("--group", help="current output ruleset name, e.g. CNMedia/TikTok")
    ap.add_argument("--processor", default="merge", help="merge|switchyomega_domain|gfw_ultimate|china_max_ip")
    ap.add_argument("--fail-on-empty", action="store_true")
    args = ap.parse_args()

    sources = load_sources(args)
    governance = load_governance(args.governance_file, args.group)
    routed_prepend, routed_drop = resolve_routed_rules(args.group, governance["routed_rules"])

    explicit_prepend = governance["prepend_rules"]
    explicit_append = governance["append_rules"]
    explicit_drop = set(governance["drop_rules"])

    prepend_rules = parse_rule_items([*routed_prepend, *explicit_prepend], f"governance:{args.group or 'default'}:prepend")
    append_rules = parse_rule_items(explicit_append, f"governance:{args.group or 'default'}:append")
    drop_rules = explicit_drop | routed_drop

    source_texts: list[tuple[str, str]] = []
    source_stats: list[dict] = []
    for src in sources:
        try:
            source_texts.append((src, read_source(src)))
        except Exception as e:
            source_stats.append({"source": redact(src), "rules": 0, "ok": False, "error": repr(e)})
            print(f"WARN failed source {redact(src)}: {e}", file=sys.stderr)

    processed_rules, processed_stats = build_rules_from_processor(args.processor, source_texts)
    source_stats.extend(processed_stats)
    all_rules = processed_rules
    ordered_rules = [*prepend_rules, *all_rules, *append_rules]

    seen: dict[tuple[str, str, tuple[str, ...]], Rule] = {}
    dup = []
    deduped = []
    dropped = []
    for r in ordered_rules:
        if r.out() in drop_rules:
            dropped.append({"rule": r.out(), "source": redact(r.source), "line": r.line, "reason": "governance_route"})
            continue
        full = (r.typ, r.value.lower(), r.options)
        if full in seen:
            dup.append({
                "rule": r.out(),
                "source": redact(r.source),
                "line": r.line,
                "first_source": redact(seen[full].source),
                "first_line": seen[full].line,
            })
            continue
        seen[full] = r
        deduped.append(r)

    final = deduped
    shadows = []
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
        *([f"# 治理配置：{args.governance_file}::{args.group or 'default'}"] if args.governance_file else []),
        f"# 处理模式：{args.processor}",
        f"# 更新时间：{update_time}",
        f"# 原始规则数：{len(all_rules)}条",
        f"# 去重后规则数：{len(deduped)}条",
        f"# 输出规则数：{len(final)}条",
        f"# 重复规则数：{len(dup)}条",
        f"# 丢弃规则数：{len(dropped)}条",
        f"# 遮蔽规则数：{len(shadows)}条",
        args.author,
        "",
    ]
    out_path.write_text("\n".join(header + [r.out() for r in final]) + "\n", encoding="utf-8")

    analysis = Path(args.analysis_dir)
    analysis.mkdir(parents=True, exist_ok=True)
    stem = out_path.stem
    summary = {
        "output": str(out_path),
        "group": args.group,
        "processor": args.processor,
        "sources": source_stats,
        "raw_rules": len(all_rules),
        "deduped_rules": len(deduped),
        "output_rules": len(final),
        "duplicates": len(dup),
        "dropped": len(dropped),
        "shadowed": len(shadows),
        "low_memory": args.low_memory,
        "governance_file": args.governance_file,
        "routed_prepend_rules": len(routed_prepend),
        "routed_drop_rules": len(routed_drop),
        "explicit_prepend_rules": len(explicit_prepend),
        "explicit_append_rules": len(explicit_append),
        "explicit_drop_rules": len(explicit_drop),
    }
    (analysis / f"{stem}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for name, rows, fields in [
        ("duplicates", dup, ["rule", "source", "line", "first_source", "first_line"]),
        ("dropped", dropped, ["rule", "source", "line", "reason"]),
        ("shadowed", shadows, ["rule", "source", "line", "shadowed_by", "shadow_source"]),
    ]:
        with (analysis / f"{stem}.{name}.tsv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
            w.writeheader()
            w.writerows(rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
