"""Classify all 46 ai_reasoning templates by output type."""
import yaml
from pathlib import Path
from collections import Counter

lib_path = Path(r'C:\Users\joelj\Downloads\kio_final\automation\library')
templates = sorted(lib_path.rglob('*.yaml'))

ai_templates = []
for t_path in templates:
    with open(t_path, encoding='utf-8-sig') as f:
        t = yaml.safe_load(f)
    if 'ai_reasoning' not in t.get('capabilities_required', []):
        continue
    
    tid = t.get('id', t_path.stem)
    steps = t.get('steps', [])
    ai_steps = [s for s in steps if s.get('capability') == 'ai_reasoning']
    outputs = t.get('outputs', [])
    
    # Classify each ai_reasoning step by action
    for s in ai_steps:
        act = s.get('action', '')
        step_inputs = s.get('inputs', {})
        step_outputs = s.get('outputs', [])
        when = s.get('when', '')
        
        # Check if it needs structured output (outputs specified + non-trivial)
        has_structured_outputs = bool(step_outputs) and len(step_outputs) > 0
        
        ai_templates.append({
            'template_id': tid,
            'action': act,
            'inputs': step_inputs,
            'outputs': step_outputs,
            'has_structured_outputs': has_structured_outputs,
            'when': when,
            'all_steps': steps,
            'all_caps': t.get('capabilities_required', []),
        })

# Count actions
action_counts = Counter(t['action'] for t in ai_templates)
print("=== AI_REASONING ACTION DISTRIBUTION ===")
for action, count in action_counts.most_common():
    print(f"  {action}: {count}")

# Classify by output type
print()
print("=== CLASSIFICATION BY OUTPUT TYPE ===")

# A. Plain text (no structured outputs)
plain_text = [t for t in ai_templates if not t['has_structured_outputs']]
print(f"A. Plain text reasoning: {len(plain_text)} steps")
for t in plain_text:
    print(f"   {t['template_id']}: {t['action']}")

# B. JSON/structured (has outputs)
structured = [t for t in ai_templates if t['has_structured_outputs']]
print(f"\nB. JSON/structured reasoning: {len(structured)} steps")
for t in structured:
    print(f"   {t['template_id']}: {t['action']} -> {t['outputs']}")

# Count unique templates per category
plain_templates = set(t['template_id'] for t in plain_text)
struct_templates = set(t['template_id'] for t in structured)
print(f"\nTemplates with ONLY plain text steps: {len(plain_templates - struct_templates)}")
print(f"Templates with ANY structured step: {len(struct_templates)}")
print(f"Templates with BOTH: {len(plain_templates & struct_templates)}")

# Also check: which templates have other dependencies beyond ai_reasoning?
print()
print("=== DEPENDENCY ANALYSIS ===")
for t_path in templates:
    with open(t_path, encoding='utf-8-sig') as f:
        t = yaml.safe_load(f)
    if 'ai_reasoning' not in t.get('capabilities_required', []):
        continue
    tid = t.get('id', t_path.stem)
    caps = t.get('capabilities_required', [])
    other_caps = [c for c in caps if c != 'ai_reasoning']
    if other_caps:
        print(f"  {tid}: ai_reasoning + {other_caps}")
