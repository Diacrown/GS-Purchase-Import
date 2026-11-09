"""
CLI entry point:

    python -m gemstone_intake.cli <intake.xlsx> <agl_responses_dir> <output.xlsx>

Example:
    python -m gemstone_intake.cli \\
        demo/sample_intake.xlsx demo/agl_responses demo/out_ezjems_import.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

from .pipeline import run_pipeline


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    intake_path = Path(argv[0]).resolve()
    agl_dir     = Path(argv[1]).resolve()
    out_path    = Path(argv[2]).resolve()

    for p in (intake_path, agl_dir):
        if not p.exists():
            print(f"error: not found: {p}", file=sys.stderr)
            return 2

    result = run_pipeline(intake_path, agl_dir, out_path)
    print(result.summary())
    for row in result.per_row:
        tag = {"ok": "✓", "partial": "⚠", "red": "✗", "failed": "✗"}.get(row["status"], "?")
        print(f"  {tag} {row['report_no']}: {row['status']} "
              f"{'| ' + '; '.join(row['warnings']) if row['warnings'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
