"""
Scenario Report Generator

Converts scenario_results.json into a Markdown summary.
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_markdown_report(results_json: str, output_md: str):
    results_path = Path(results_json)
    if not results_path.exists():
        print(f"Error: {results_json} not found.")
        return

    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats = data["stats"]
    timestamp = data["timestamp"]
    results = data["results"]

    with open(output_md, "w", encoding="utf-8") as f:
        f.write("# Gate 1.5 Scenario Hardening Report\n\n")
        f.write(f"**Generated:** {timestamp}\n\n")
        
        f.write("## Summary Statistics\n\n")
        f.write(f"- **Total Scenarios:** {stats['total']}\n")
        f.write(f"- **Passed:** {stats['passed']}\n")
        f.write(f"- **Failed:** {stats['failed']}\n")
        
        pass_rate = (stats['passed'] / stats['total'] * 100) if stats['total'] > 0 else 0
        f.write(f"- **Pass Rate:** {pass_rate:.1f}%\n\n")

        # Category breakdown
        categories = {}
        for r in results:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "passed": 0}
            categories[cat]["total"] += 1
            if r["passed"]:
                categories[cat]["passed"] += 1

        f.write("## Category Breakdown\n\n")
        f.write("| Category | Passed | Total | Rate |\n")
        f.write("|----------|--------|-------|------|\n")
        for cat, s in categories.items():
            rate = (s['passed'] / s['total'] * 100)
            f.write(f"| `{cat}` | {s['passed']} | {s['total']} | {rate:.1f}% |\n")
        f.write("\n")

        f.write("## Detailed Results\n\n")
        f.write("| ID | Category | Input | Result | Error / Note |\n")
        f.write("|----|----------|-------|--------|--------------|\n")
        for r in results:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            error = r["error"] or "-"
            f.write(f"| {r['id']} | `{r['category']}` | `{r['input']}` | {status} | {error} |\n")

    print(f"[REPORT] Markdown report generated: {output_md}")


if __name__ == "__main__":
    generate_markdown_report("scenario_results.json", "SCENARIO_REPORT.md")
