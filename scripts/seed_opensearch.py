#!/usr/bin/env python3
"""ApexMotion Supplier Risk Intelligence Platform — OpenSearch Vector Seeder CLI.

Executes k-NN index provisioning and 500-clause vector seeding against
Amazon OpenSearch Service or local vector store.

Usage:
    python scripts/seed_opensearch.py [--dry-run] [--clear] [--verify] [--batch-size 100]

Options:
    --dry-run       Simulate clause generation in memory with zero external network I/O
    --clear         Purge and re-provision index before seeding
    --verify        Execute post-seed integrity verification checks
    --verify-only   Run integrity verification checks without re-seeding
    --endpoint      OpenSearch host endpoint (default from settings or localhost)
    --index-name    Target vector index name (default: contracts-v1)
    --batch-size    Bulk index chunk size (default: 100)
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import get_settings  # noqa: E402
from src.core.logging import get_logger  # noqa: E402
from src.database.opensearch_client import OpenSearchClient  # noqa: E402
from src.database.seed_opensearch import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    DEFAULT_INDEX_NAME,
    build_synthetic_contract_clauses,
    seed_opensearch,
    verify_opensearch_seed_integrity,
)

logger = get_logger("apexmotion.scripts.seed_opensearch")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ApexMotion OpenSearch k-NN Vector Seeder",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate clause generation in memory with zero network I/O",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Purge existing index before seeding",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Execute post-seed integrity verification checks",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Run integrity verification without seeding",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=None,
        help="OpenSearch endpoint (default from OPENSEARCH_ENDPOINT settings)",
    )
    parser.add_argument(
        "--index-name",
        type=str,
        default=DEFAULT_INDEX_NAME,
        help=f"Target vector index name (default: {DEFAULT_INDEX_NAME})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of documents per bulk index batch (default: {DEFAULT_BATCH_SIZE})",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    endpoint = args.endpoint or settings.OPENSEARCH_ENDPOINT
    index_name = args.index_name or settings.OPENSEARCH_INDEX_CONTRACTS

    print("=================================================================")
    print("  ApexMotion OpenSearch Vector Seeder (500 Contract Clauses)     ")
    print("=================================================================")
    print(f"  Endpoint:    {endpoint}")
    print(f"  Index:       {index_name}")
    print(f"  Dry Run:     {args.dry_run}")
    print(f"  Clear First: {args.clear}")
    print("=================================================================\n")

    if args.dry_run:
        print("[dry-run] Generating 500 synthetic contract clauses in memory...")
        clauses = build_synthetic_contract_clauses()
        print(
            f"[dry-run] Generated {len(clauses)} clauses across {len({c.contract_id for c in clauses})} contracts."
        )
        print(f"[dry-run] Sample clause 1 ID: {clauses[0].chunk_id}")
        print(f"[dry-run] Sample clause 1 Category: {clauses[0].clause_category}")
        print(f"[dry-run] Vector dimension: {len(clauses[0].embedding_vector)}")
        print("[dry-run] Dry-run verification completed successfully.")
        return 0

    client = OpenSearchClient(endpoint=endpoint)
    try:
        if not args.verify_only:
            print(f"[*] Provisioning index and bulk-indexing into '{index_name}'...")
            result = await seed_opensearch(
                client=client,
                index_name=index_name,
                clear_existing=args.clear,
                batch_size=args.batch_size,
            )
            print(
                f"[+] Seeding successful: {result.total_clauses} clauses across {result.total_suppliers} suppliers in {result.elapsed_seconds}s"
            )
            print(f"[+] Batches committed: {result.batch_count}")

        if args.verify or args.verify_only:
            print("\n[*] Executing post-seed integrity verification...")
            integrity = await verify_opensearch_seed_integrity(client=client, index_name=index_name)
            if integrity["is_valid"]:
                print(
                    "[+] Integrity Audit: PASSED (Index exists, canonical clauses present, k-NN queries operational)"
                )
            else:
                print("[-] Integrity Audit: FAILED")
                for discrepancy in integrity.get("discrepancies", []):
                    print(f"    - {discrepancy}")
                return 1

        print("\n[+] OpenSearch vector seeding workflow completed successfully.")
        return 0
    finally:
        await client.close()


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
