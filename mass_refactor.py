import os
import re
import sys

# Ensure stdout uses utf-8 on windows
sys.stdout.reconfigure(encoding='utf-8')

css_dir = r"d:\Ai-mentor\frontend\src"

def process_css_file(filepath):
    # Skip standard global files unless we really want them
    if filepath.endswith('index.css') or filepath.endswith('tokens.css'):
        return

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    original_content = content

    # --- BACKGROUNDS ---
    # Replace white/light backgrounds with dark surfaces
    content = re.sub(r'background(?:-color)?:\s*(?:#ffffff|#fff|white|#f9fafb|#f3f4f6|var\(--bg-primary\));', 'background-color: var(--surface, #141414);', content, flags=re.IGNORECASE)
    content = re.sub(r'background(?:-color)?:\s*rgba\(255,\s*255,\s*255,\s*[\d.]+\);', 'background-color: var(--surface-2, #1E1E1E);', content, flags=re.IGNORECASE)

    # --- TEXT COLORS ---
    # Dark text to light text
    content = re.sub(r'color:\s*(?:#333333|#333|#1f2937|#111827|#4b5563|#6b7280|var\(--text-primary\));', 'color: var(--text-1, #FAFAFA);', content, flags=re.IGNORECASE)
    
    # --- BORDERS ---
    # Remove border radius completely
    content = re.sub(r'border-radius:\s*(?:\d+(?:px|rem|em|%)|var\(--[a-zA-Z0-9-]+\));', 'border-radius: 0;', content)
    # Convert soft borders to sharp dark borders
    content = re.sub(r'border:\s*\d+px\s+solid\s+(?:#[A-Fa-f0-9]+|rgba?\(.*?\)|var\(--[a-zA-Z0-9-]+\));', 'border: 2px solid var(--border, #333333);', content, flags=re.IGNORECASE)
    content = re.sub(r'border-[a-z]+:\s*\d+px\s+solid\s+(?:#[A-Fa-f0-9]+|rgba?\(.*?\)|var\(--[a-zA-Z0-9-]+\));', lambda m: m.group(0).split('solid')[0] + 'solid var(--border, #333333);', content, flags=re.IGNORECASE)

    # --- SHADOWS ---
    # Convert all soft drop shadows to neo-brutalist strong offset shadows
    content = re.sub(r'box-shadow:\s*(?!none\b)[^;]+;', 'box-shadow: 4px 4px 0px var(--accent, #CCFF00);', content, flags=re.IGNORECASE)

    # --- GRADIENTS ---
    # Attempt to replace gradients that look soft
    content = re.sub(r'background(?:-image)?:\s*linear-gradient\([^;]+;', 'background: var(--surface-2, #1E1E1E);', content, flags=re.IGNORECASE)
    
    # --- ACCENT COLORS ---
    # Replace anything looking like an active/primary blue with acid green
    content = re.sub(r':\s*(?:#3b82f6|#2563eb|#4f46e5|#6366f1|var\(--primary-color\));', ': var(--accent, #CCFF00);', content, flags=re.IGNORECASE)

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(content)
        print(f"Refactored: {filepath}")

for root, dirs, files in os.walk(css_dir):
    for f in files:
        if f.endswith('.css'):
            process_css_file(os.path.join(root, f))

print("DONE processing CSS files.")
