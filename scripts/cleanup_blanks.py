import re
from pathlib import Path

p = Path(r"c:\Users\admin\Desktop\Production Monitor\Python\1.py")
text = p.read_text(encoding="utf-8")

# Remove blank lines that are not inside triple-quoted strings
out_lines = [l for l in text.splitlines() if l.replace('\u00A0','').strip() != '']

new_text = "\n".join(out_lines) + "\n"

p.write_text(new_text, encoding="utf-8")
print(f"Cleaned {p}")
