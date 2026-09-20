"""Extract complete dependency data from all 63 automation templates."""
import yaml
from pathlib import Path
import json

lib_path = Path(r'C:\Users\joelj\Downloads\kio_final\automation\library')
templates = sorted(lib_path.rglob('*.yaml'))

# Runtime availability (current state)
AVAILABLE_CAPS = {'workflow', 'memory', 'browser', 'filesystem', 'terminal', 'artifact'}

results = []
for t_path in templates:
    try:
        with open(t_path, encoding='utf-8-sig') as f:
            t = yaml.safe_load(f)
        
        template_id = t.get('id', t_path.stem)
        template_name = t.get('name', '')
        caps_required = t.get('capabilities_required', [])
        caps_set = set(caps_required)
        
        # Extract all step actions
        steps = t.get('steps', [])
        step_actions = []
        for s in steps:
            cap = s.get('capability', '')
            act = s.get('action', '')
            step_id = s.get('id', '')
            depends = s.get('depends_on', [])
            when = s.get('when', '')
            step_actions.append({
                'id': step_id,
                'capability': cap,
                'action': act,
                'depends_on': depends,
                'when': when,
            })
        
        # Classify
        caps_unavailable = caps_set - AVAILABLE_CAPS
        
        # Check verification requirements
        verification = t.get('verification', [])
        security = t.get('security_classification', '')
        idempotency = t.get('failure_recovery', {}).get('idempotency_key', '')
        
        # Provider requirements
        providers_required = t.get('providers_required', [])
        credentials_required = t.get('credentials_required', [])
        
        rel_path = str(t_path.relative_to(lib_path))
        
        results.append({
            'path': rel_path,
            'id': template_id,
            'name': template_name,
            'caps_required': sorted(caps_set),
            'caps_unavailable': sorted(caps_unavailable),
            'steps': step_actions,
            'providers_required': providers_required,
            'credentials_required': [c.get('name', '') for c in (credentials_required or [])],
            'verification': bool(verification),
            'security': security,
            'idempotency': bool(idempotency),
        })
    except Exception as e:
        print(f"ERROR parsing {t_path}: {e}")

# Output as JSON for analysis
print(json.dumps(results, indent=2))
