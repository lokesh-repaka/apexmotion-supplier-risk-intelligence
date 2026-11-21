#!/usr/bin/env python3
"""
ApexMotion Antigravity Token & Cost Governance Tracker
Analyzes token usage, model tier allocation, context caching efficiency,
and calculates estimated API costs across Gemini models (Pro, Flash, Flash-Lite).
"""

import glob
import json
import os
from pathlib import Path

# Gemini 1.5 / 2.0 Antigravity standard pricing (USD per 1M tokens)
# Source: Google Cloud / Gemini API Pricing tiers (<128k prompt context)
PRICING = {
    "pro": {
        "prompt": 1.25,
        "cached_prompt": 0.3125,  # 75% cache discount
        "completion": 5.00,
    },
    "flash": {
        "prompt": 0.075,
        "cached_prompt": 0.01875,  # 75% cache discount
        "completion": 0.30,
    },
    "flash_lite": {
        "prompt": 0.01875,
        "cached_prompt": 0.0046875,  # 75% cache discount
        "completion": 0.075,
    },
}


def find_transcripts():
    """Find available Antigravity transcript logs in brain directory."""
    home = Path.home()
    patterns = [
        str(home / ".gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl"),
        str(home / ".gemini/antigravity/brain/*/transcript.jsonl"),
    ]
    matches = []
    for pat in patterns:
        matches.extend(glob.glob(pat))
    return sorted(matches, key=os.path.getmtime, reverse=True)


def parse_transcript(transcript_path):
    """Parse transcript.jsonl to extract token counts and model calls."""
    data = {
        "pro": {"prompt": 0, "cached": 0, "completion": 0, "turns": 0},
        "flash": {"prompt": 0, "cached": 0, "completion": 0, "turns": 0},
        "flash_lite": {"prompt": 0, "cached": 0, "completion": 0, "turns": 0},
    }

    if not os.path.exists(transcript_path):
        return data

    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue

            # Check model name or step type
            model = entry.get("modelName", "").lower()
            tier = "flash"
            if "pro" in model:
                tier = "pro"
            elif "lite" in model or "haiku" in model:
                tier = "flash_lite"

            usage = entry.get("token_usage") or entry.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
            cached_tokens = usage.get("cached_tokens") or usage.get("cached_prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)

            data[tier]["prompt"] += max(0, prompt_tokens - cached_tokens)
            data[tier]["cached"] += cached_tokens
            data[tier]["completion"] += completion_tokens
            data[tier]["turns"] += 1

    return data


def calculate_costs(usage_data):
    """Calculate USD spend and cache savings."""
    report = []
    total_cost = 0.0
    total_unoptimized_cost = 0.0

    for tier, rates in PRICING.items():
        stats = usage_data.get(tier, {"prompt": 0, "cached": 0, "completion": 0, "turns": 0})
        prompt_cost = (stats["prompt"] / 1_000_000) * rates["prompt"]
        cached_cost = (stats["cached"] / 1_000_000) * rates["cached_prompt"]
        comp_cost = (stats["completion"] / 1_000_000) * rates["completion"]
        tier_cost = prompt_cost + cached_cost + comp_cost

        # Unoptimized cost assumes no context cache discount
        unopt = ((stats["prompt"] + stats["cached"]) / 1_000_000) * rates["prompt"] + comp_cost

        total_cost += tier_cost
        total_unoptimized_cost += unopt

        report.append(
            {
                "tier": tier,
                "turns": stats["turns"],
                "prompt_tokens": stats["prompt"],
                "cached_tokens": stats["cached"],
                "completion_tokens": stats["completion"],
                "cost_usd": tier_cost,
                "savings_usd": max(0.0, unopt - tier_cost),
            }
        )

    return report, total_cost, max(0.0, total_unoptimized_cost - total_cost)


def generate_markdown_report(report, total_cost, total_savings, transcript_name="Current / Active"):
    lines = [
        "# ApexMotion Antigravity Token & Cost Governance Report",
        f"**Source**: `{transcript_name}`",
        "",
        "| Model Tier | Turns | New Prompt | Cached Prompt | Completion | Cost (USD) | Cache Savings |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report:
        lines.append(
            f"| `{row['tier']}` | {row['turns']} | {row['prompt_tokens']:,} | {row['cached_tokens']:,} | "
            f"{row['completion_tokens']:,} | ${row['cost_usd']:.4f} | ${row['savings_usd']:.4f} |"
        )
    lines.append("")
    lines.append(f"**Total Session Cost**: **${total_cost:.4f} USD**")
    lines.append(
        f"**Context Cache Savings**: **${total_savings:.4f} USD** (75% discount applied on cached prefixes)"
    )
    return "\n".join(lines)


def main():
    transcript_files = find_transcripts()
    if transcript_files:
        transcript_path = transcript_files[0]
        usage_data = parse_transcript(transcript_path)
        source_name = os.path.basename(os.path.dirname(os.path.dirname(transcript_path)))
    else:
        # Fallback baseline model demonstration
        usage_data = {
            "pro": {"prompt": 25000, "cached": 65000, "completion": 2800, "turns": 3},
            "flash": {"prompt": 45000, "cached": 180000, "completion": 8500, "turns": 18},
            "flash_lite": {"prompt": 12000, "cached": 50000, "completion": 1200, "turns": 6},
        }
        source_name = "Baseline Governance Profile (Mock Simulation)"

    report, total_cost, total_savings = calculate_costs(usage_data)
    md = generate_markdown_report(report, total_cost, total_savings, source_name)
    print(md)


if __name__ == "__main__":
    main()
