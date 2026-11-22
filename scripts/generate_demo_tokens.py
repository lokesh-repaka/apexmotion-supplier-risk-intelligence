#!/usr/bin/env python3
"""CLI utility to generate signed demo Okta JWT tokens for platform personas.

Supported formats:
  - text (default): Human-readable terminal output with summary table & curl headers
  - json: Structured JSON payload for automated test runners and CI pipelines
  - env: Shell export environment variables format for local .env testing

Usage:
  python3 scripts/generate_demo_tokens.py --format text
  python3 scripts/generate_demo_tokens.py --format json --output tokens.json
  python3 scripts/generate_demo_tokens.py --format env > .env.demo
"""

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path when invoked directly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.core.demo_auth import (  # noqa: E402
    DEMO_PERSONAS,
    generate_all_demo_tokens,
)


def format_text(tokens: dict[str, str], expires_hours: float) -> str:
    """Format tokens and persona info as a human-readable console dashboard."""
    lines: list[str] = [
        "=" * 80,
        "  ApexMotion Demo Persona Tokens (Local Okta / JWT SSO Simulation)",
        f"  Valid for: {expires_hours:.1f} hours | Issuer: okta-demo-issuer | Audience: apexmotion-api",
        "=" * 80,
        "",
    ]

    for p_id, persona in DEMO_PERSONAS.items():
        token = tokens[p_id]
        spend_str = (
            f"${persona.spend_authority_usd:,.2f}"
            if persona.spend_authority_usd is not None
            else "N/A (System)"
        )
        lines.append(f"Persona: [{p_id.upper()}]")
        lines.append(f"  Name:            {persona.name}")
        lines.append(f"  User ID:         {persona.user_id}")
        lines.append(f"  Email:           {persona.email}")
        lines.append(f"  Role:            {persona.role.value}")
        lines.append(f"  Spend Limit:     {spend_str}")
        lines.append(f"  Groups:          {', '.join(persona.groups)}")
        lines.append(f"  Description:     {persona.description}")
        lines.append("  Authorization: Bearer " + token)
        lines.append(
            f'  Example curl:    curl -H "Authorization: Bearer {token}" http://localhost:8000/api/v1/health'
        )
        lines.append("-" * 80)

    lines.append("")
    lines.append("To export into your shell environment, run:")
    lines.append("  eval $(python3 scripts/generate_demo_tokens.py --format env)")
    lines.append("=" * 80)
    return "\n".join(lines)


def format_json(tokens: dict[str, str]) -> str:
    """Format tokens and personas as structured JSON."""
    personas_dict: dict[str, Any] = {}
    for p_id, p in DEMO_PERSONAS.items():
        personas_dict[p_id] = {
            "persona_id": p.persona_id,
            "user_id": p.user_id,
            "name": p.name,
            "email": p.email,
            "role": p.role.value,
            "roles": p.roles,
            "groups": p.groups,
            "spend_authority_usd": str(p.spend_authority_usd)
            if p.spend_authority_usd is not None
            else None,
            "description": p.description,
        }

    output_data = {
        "tokens": tokens,
        "personas": personas_dict,
    }
    return json.dumps(output_data, indent=2)


def format_env(tokens: dict[str, str]) -> str:
    """Format tokens as bash environment variable exports."""
    lines = [
        "# ApexMotion Demo Okta JWT Tokens",
        "# Generated automatically via scripts/generate_demo_tokens.py",
    ]
    for p_id, token in tokens.items():
        env_var_name = f"DEMO_TOKEN_{p_id.upper()}"
        lines.append(f'{env_var_name}="{token}"')
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate signed Okta demo tokens for ApexMotion platform personas.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "env"],
        default="text",
        help="Output format: text (default), json, or env",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Optional destination file path to save output",
    )
    parser.add_argument(
        "--expires-hours",
        type=float,
        default=24.0,
        help="Token validity duration in hours (default: 24.0)",
    )

    args = parser.parse_args()

    expires_delta = timedelta(hours=args.expires_hours)
    tokens = generate_all_demo_tokens(expires_delta=expires_delta)

    if args.format == "json":
        content = format_json(tokens)
    elif args.format == "env":
        content = format_env(tokens)
    else:
        content = format_text(tokens, args.expires_hours)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        print(f"Tokens written successfully to {args.output}")
    else:
        print(content)


if __name__ == "__main__":
    main()
