"""Phase 4C: Post-P1 template re-evaluation.

Scans all 63 YAML templates, maps each step's (capability, action) to its
execution_boundary action, and classifies templates as:
  - FULLY_EXECUTABLE: all steps have working boundary actions
  - ROUTING_WORKS: execute_capability format is now correct but provider may be missing
  - BLOCKED: still has a format or routing issue
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

_library_root = Path(r"C:\Users\joelj\Downloads\kio_final\automation\library")

# Import the action map from step_runner
from mini_kio.automation.step_runner import StepRunner

_ACTION_MAP = StepRunner._ACTION_MAP


def classify_templates():
    """Load all templates and classify their executable status."""
    from mini_kio.automation.template_store import TemplateStore

    store = TemplateStore(_library_root)
    count = store.load()
    print(f"Loaded {count} templates\n")

    results = {
        "FULLY_EXECUTABLE": [],
        "ROUTING_WORKS": [],
        "BLOCKED": [],
        "UNKNOWN_ACTION": [],
    }

    for tid, template_record in store._templates.items():
        steps = template_record.steps
        template_class = "FULLY_EXECUTABLE"
        blocked_reasons = []

        for step in steps:
            capability = step.get("capability", "")
            action = step.get("action", "")
            boundary_action = _ACTION_MAP.get((capability, action))

            if boundary_action is None:
                # Unknown (capability, action) pair
                template_class = "UNKNOWN_ACTION"
                blocked_reasons.append(f"({capability}.{action}) -> no _ACTION_MAP entry")
            elif boundary_action == "execute_capability":
                # After P1 fix, format is correct. Provider may be missing.
                if template_class != "UNKNOWN_ACTION":
                    template_class = "ROUTING_WORKS"
            else:
                # Direct boundary action (browser_goto, read_file, write_csv, etc.)
                pass  # These work fine

        results[template_class].append({
            "id": tid,
            "category": template_record.category,
            "steps": len(steps),
            "blocked_reasons": blocked_reasons,
        })

    return results


def print_report(results):
    """Print the post-P1 classification report."""
    print("=" * 70)
    print("POST-P1 TEMPLATE CLASSIFICATION")
    print("=" * 70)

    for status, templates in results.items():
        print(f"\n--- {status}: {len(templates)} templates ---")
        for t in templates:
            reasons = f" [{', '.join(t['blocked_reasons'])}]" if t['blocked_reasons'] else ""
            print(f"  {t['id']:50s} cat={t['category']:20s} steps={t['steps']}{reasons}")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY:")
    for status, templates in results.items():
        print(f"  {status:25s}: {len(templates)}")
    print(f"  {'TOTAL':25s}: {sum(len(v) for v in results.values())}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    results = classify_templates()
    print_report(results)
