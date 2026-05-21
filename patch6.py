with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\app_operator.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.startswith('def _refine_pid_windows('):
        start_idx = i
        break

if start_idx != -1:
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith('def _launch_from_info('):
            end_idx = i
            break

if start_idx != -1 and end_idx != -1:
    with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\temp_refine2.py', 'r', encoding='utf-8-sig') as f:
        new_refine = f.read()
        
    new_lines = lines[:start_idx] + [new_refine + "\n\n"] + lines[end_idx:]
    
    with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\app_operator.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Patched correctly.")
else:
    print("Could not find bounds")
