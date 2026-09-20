import yaml, os, json

library_dir = r'C:\Users\joelj\Downloads\kio_final\automation\library'

# Find all templates using terminal::append_xlsx_row
for root, dirs, files in os.walk(library_dir):
    for f in sorted(files):
        if not f.endswith('.yaml'):
            continue
        path = os.path.join(root, f)
        rel = os.path.relpath(path, library_dir).replace('\\', '/')
        with open(path, 'r', encoding='utf-8') as fh:
            data = yaml.safe_load(fh)
        
        steps = data.get('steps', [])
        for s in steps:
            if s.get('capability') == 'terminal' and s.get('action') == 'append_xlsx_row':
                print(f'=== {rel} ===')
                print(f'ID: {data.get("id", "unknown")}')
                print(f'Capabilities: {data.get("capabilities_required", [])}')
                print(f'Steps:')
                for st in steps:
                    print(f'  - {st.get("capability")}::{st.get("action")}')
                    if st.get('capability') == 'terminal' and st.get('action') == 'append_xlsx_row':
                        print(f'    Inputs: {json.dumps(st.get("inputs", {}))}')
                        print(f'    Outputs: {st.get("outputs", [])}')
                        print(f'    Verification: {st.get("verification", {})}')
                        print(f'    Idempotency: {st.get("idempotency", {})}')
                        print(f'    Security: {st.get("security", {})}')
                        print(f'    Confirmation: {st.get("confirmation", {})}')
                print()
                # Print full YAML for reference
                print('Full YAML:')
                print(json.dumps(data, indent=2))
