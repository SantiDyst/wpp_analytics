# ---
# date: 2026-07-04
# ---
"""Read taxonomias_seed/medical_licenses.yaml and write outputs/taxonomia_<client>_v1.yaml.

Usage:
    python scripts/bootstrap_taxonomy.py
    python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/medical_licenses.yaml --client auto_wpp
"""

import sys
import os
import argparse
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: pyyaml is not installed. Please run 'pip install pyyaml'.\n")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap a client-specific taxonomy file from a seed YAML file."
    )
    parser.add_argument(
        "--seed",
        default="taxonomias_seed/medical_licenses.yaml",
        help="Path to the seed taxonomy YAML file."
    )
    parser.add_argument(
        "--client",
        default="auto_wpp",
        help="Client name to bootstrap the taxonomy for."
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory to write the bootstrapped taxonomy file to."
    )
    args = parser.parse_args()

    seed_path = Path(args.seed)
    if not seed_path.exists():
        sys.stderr.write(f"ERROR: Seed file not found at '{seed_path}'\n")
        sys.exit(1)

    try:
        content = seed_path.read_text(encoding='utf-8')
        data = yaml.safe_load(content)
    except Exception as e:
        sys.stderr.write(f"ERROR: Failed to parse seed YAML file: {e}\n")
        sys.exit(1)

    if not isinstance(data, dict) or 'categories' not in data:
        sys.stderr.write("ERROR: Invalid seed taxonomy structure. Must contain a 'categories' key.\n")
        sys.exit(1)

    # Sanitize client name
    sanitized_client = re.sub(r"[^A-Za-z0-9_-]", "_", args.client)

    # Output directory
    output_dir = Path(args.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        sys.stderr.write(f"ERROR: Failed to create output directory '{output_dir}': {e}\n")
        sys.exit(1)

    output_path = output_dir / f"taxonomia_{sanitized_client}_v1.yaml"

    try:
        output_path.write_text(content, encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"ERROR: Failed to write output file '{output_path}': {e}\n")
        sys.exit(1)

    categories = data['categories']
    n_categories = len(categories)
    n_subcategories = sum(len(subcats) for subcats in categories.values() if isinstance(subcats, dict))

    print(f"Wrote outputs/taxonomia_{sanitized_client}_v1.yaml ({n_categories} categories, {n_subcategories} subcategories)")

if __name__ == "__main__":
    main()
