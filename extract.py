#!/usr/bin/env python3
"""Pull the figures used in this report out of Artificial Analysis's own pages.

The site embeds its chart data in each page as a Next.js payload. This script
downloads two pages, decodes that payload and writes the rows the report uses
to data/. Standard library only.

    python3 extract.py
"""
import csv
import json
import re
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MODEL_PAGE = "https://artificialanalysis.ai/models/claude-opus-5-5"
AGENT_PAGE = "https://artificialanalysis.ai/agents/coding-agents"

# Model families that Artificial Analysis has run at more than one effort setting.
FAMILIES = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "gpt-6-astra",
            "gpt-6-1-sol", "gpt-6-sol", "grok-4-7", "gemini-3-8-flash")
AGENTS = ("Claude Code", "Codex")


def payload(url):
    """Return the page's embedded data as one decoded string."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, flags=re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def objects(text, start_pattern):
    """Yield every JSON object in text that begins at a match of start_pattern."""
    decoder = json.JSONDecoder()
    for m in re.finditer(start_pattern, text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj


def effort(name):
    m = re.search(r"\((?:[^()]*?\b)?(low|medium|high|xhigh|max)\b", name, flags=re.I)
    return m.group(1).lower() if m else ""


def intelligence_index_rows():
    seen = {}
    for o in objects(payload(MODEL_PAGE), r'\{"id":"[0-9a-f-]{36}"'):
        slug = o.get("slug", "")
        if not slug.startswith(FAMILIES) or not o.get("intelligenceIndexCostPerTask"):
            continue
        if len(o) < len(seen.get(slug, {})):
            continue
        seen[slug] = o
    for slug, o in sorted(seen.items()):
        cost = o["intelligenceIndexCostPerTask"]["cost"]
        evals = {e["slug"]: e for e in o.get("intelligenceIndexEvaluations") or []}
        tb = evals.get("terminalbench-4-0", {})
        tokens = o.get("canonicalIntelligenceIndexTokenCount") or {}
        yield {
            "slug": slug,
            "name": o.get("shortName") or o.get("name"),
            "effort": effort(o.get("shortName") or o.get("name") or ""),
            "index_score": round(o["intelligenceIndex"], 1) if o.get("intelligenceIndex") else "",
            "cost_per_task_usd": round(cost["total"], 3),
            "cache_hit_usd": round(cost["cacheRead"], 3),
            "cache_write_usd": round(cost["cacheWrite"], 3),
            "uncached_input_usd": round(cost["nonCacheInput"], 3),
            "reasoning_usd": round(cost["reasoning"], 3),
            "answer_usd": round(cost["answer"], 3),
            "cost_to_run_index_usd": round(o["intelligenceIndexCost"]["total"]),
            "input_tokens": tokens.get("input", ""),
            "output_tokens": tokens.get("output", ""),
            "terminal_bench_4_pass_rate": round(tb["score"], 4) if tb.get("score") is not None else "",
            "terminal_bench_4_cost_per_task_usd": round(tb["costPerTask"], 2) if tb.get("costPerTask") else "",
        }


def coding_agent_rows():
    seen = {}
    for o in objects(payload(AGENT_PAGE), r'\{"id":"[0-9a-f]{32}","isDefault"'):
        if o.get("agentName") in AGENTS and o.get("mean"):
            seen[o["id"]] = o
    for o in sorted(seen.values(), key=lambda o: -(o.get("indexScore") or 0)):
        mean = o["mean"]
        label = re.sub(r"\s*\(\{.*\}\)", "", o["displayLabel"])
        yield {
            "agent_and_model": label,
            "effort": effort(label),
            "index_score": round(o["indexScore"] * 100, 1),
            "cost_per_task_usd": round(mean["costUsd"], 2),
            "wall_time_min": round(mean["agentWallTimeSec"] / 60, 1),
            "steps": round(mean["steps"]),
            "input_tokens": round(mean["inputTokens"]),
            "output_tokens": round(mean["outputTokens"]),
            "cache_hit_rate": round(mean["cacheHitRate"], 3),
        }


def write(path, rows):
    rows = list(rows)
    if not rows:
        raise SystemExit(f"no rows found for {path}; the page layout may have changed")
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{path}: {len(rows)} rows")


if __name__ == "__main__":
    out = Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    write(out / "intelligence_index.csv", intelligence_index_rows())
    write(out / "coding_agent_index.csv", coding_agent_rows())
