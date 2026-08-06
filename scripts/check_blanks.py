from pathlib import Path
p=Path(r"c:\Users\admin\Desktop\Production Monitor\Python\1.py")
text=p.read_text(encoding='utf-8')
lines=text.splitlines()
print('total',len(lines))
print('blank_strip',sum(1 for l in lines if l.strip()==''))
print('blank_nbsp',sum(1 for l in lines if l.replace('\u00A0','').strip()==''))
print('sample_lines:')
for i,l in enumerate(lines[:40],1):
    print(i,repr(l))
