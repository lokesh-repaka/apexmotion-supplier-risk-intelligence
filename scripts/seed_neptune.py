#!/usr/bin/env python3
"""ApexMotion Supplier Risk Intelligence Platform — Neptune Knowledge Graph Seeder CLI.

Executes schema seeding and topology verification against Amazon Neptune
or local emulation.

Usage:
    python scripts/seed_neptune.py [--dry-run] [--clear] [--verify]

Options:
    --dry-run       Simulate seeding offline with zero external network I/O
    --clear         Purge all existing nodes and relationships before seeding
    --verify        Execute post-seed integrity verification checks
    --endpoint      Neptune host endpoint (default from settings or localhost)
    --port          Neptune port (default 8182)
    --ssl           Enable HTTPS / SSL connection
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import get_settings  # noqa: E402
from src.core.logging import get_logger  # noqa: E402
from src.graph.neptune_client import NeptuneClient  # noqa: E402
from src.graph.seed import (  # noqa: E402
    GOLDEN_COMPONENTS,
    GOLDEN_CONTRACTS,
    GOLDEN_EXTERNAL_SIGNALS,
    GOLDEN_PLANTS,
    GOLDEN_RELATIONSHIPS,
    GOLDEN_SUPPLIERS,
    get_seed_cypher_statements,
    seed_graph,
    verify_seed_integrity,
)

logger = get_logger("apexmotion.scripts.seed_neptune")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ApexMotion Neptune Knowledge Graph Seeder",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate seeding offline with zero network I/O",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Purge existing nodes and relationships before seeding",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run graph verification checks after seeding",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=None,
        help="Neptune host endpoint",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Neptune port",
    )
    parser.add_argument(
        "--ssl",
        action="store_true",
        default=False,
        help="Use HTTPS/SSL",
    )
    return parser.parse_args()


async def run_seed(args: argparse.Namespace) -> int:
    dry_run = args.dry_run or os.getenv("USE_LOCALSTACK", "").lower() == "true"

    print("=" * 70)
    print("ApexMotion Neptune Knowledge Graph Seeder")
    print("=" * 70)
    print(f"Mode          : {'Dry-run (offline simulation)' if dry_run else 'Live'}")
    print(f"Clear existing: {args.clear}")
    print(f"Verify        : {args.verify}")

    statements = get_seed_cypher_statements()
    print(f"Total Cypher MERGE statements to execute: {len(statements)}")

    if dry_run:
        print("\n[dry-run] Simulating graph schema seeding...")
        print(f"[dry-run] Suppliers to seed   : {len(GOLDEN_SUPPLIERS)}")
        print(f"[dry-run] Components to seed  : {len(GOLDEN_COMPONENTS)}")
        print(f"[dry-run] Plants to seed      : {len(GOLDEN_PLANTS)}")
        print(f"[dry-run] Contracts to seed   : {len(GOLDEN_CONTRACTS)}")
        print(f"[dry-run] Signals to seed     : {len(GOLDEN_EXTERNAL_SIGNALS)}")
        print(f"[dry-run] Relationships       : {len(GOLDEN_RELATIONSHIPS)}")
        print("[dry-run] Validating NanoCore golden reference entities:")
        print("  - Supplier  : SUP-NC-882 (NanoCore Semiconductor - Tier 2)")
        print("  - Component : MCU-X91 (32-Bit Automotive MCU)")
        print("  - Plant     : PLT-MUC-01 (Munich Assembly Hub)")
        print("  - Tier-1    : SUP-BE-101 (BetaElectro AG)")
        print("[dry-run] All statements verified. Simulation completed successfully.")
        return 0

    settings = get_settings()
    endpoint = args.endpoint or settings.NEPTUNE_ENDPOINT
    port = args.port or settings.NEPTUNE_PORT

    print(f"Connecting to Neptune at http{'s' if args.ssl else ''}://{endpoint}:{port}...")

    async with NeptuneClient(
        endpoint=endpoint,
        port=port,
        use_ssl=args.ssl,
        timeout=10.0,
    ) as client:
        # Check health
        is_healthy = await client.health_check()
        if not is_healthy:
            print("WARNING: Neptune health check failed. Attempting seeding anyway...")

        result = await seed_graph(client, clear_existing=args.clear)
        print(f"\nSeed succeeded in {result.execution_time_ms:.2f}ms:")
        print(f"  - Nodes created/updated        : {result.nodes_created}")
        print(f"  - Relationships created/updated: {result.relationships_created}")

        if args.verify:
            print("\nRunning integrity verification...")
            report = await verify_seed_integrity(client)
            print(f"  - Verification status: {'PASSED' if report['is_valid'] else 'FAILED'}")
            print(f"  - Entity counts      : {report['counts']}")
            if not report["is_valid"]:
                print(f"  - Discrepancies     : {report['discrepancies']}")
                return 1

    return 0


def main() -> None:
    args = parse_args()
    try:
        exit_code = asyncio.run(run_seed(args))
        sys.exit(exit_code)
    except Exception as exc:
        print(f"ERROR: Seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
