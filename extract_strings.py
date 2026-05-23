import re, os, json

files = ['editor.py', 'popup_window.py', 'notifier.py', 'main.py', 'config.py', 'memory.py']
strings = set()

for fn in files:
    if not os.path.exists(fn):
        continue
    with open(fn, 'r', encoding='utf-8') as f:
        content = f.read()
    for m in re.finditer(r'"([^"]*[\u4e00-\u9fff][^"]*)"', content):
        s = m.group(1).strip()
        if len(s) > 1:
            strings.add(s)
    for m in re.finditer(r"'([^']*[\u4e00-\u9fff][^']*)'", content):
        s = m.group(1).strip()
        if len(s) > 1:
            strings.add(s)

strings = sorted(strings)
for s in strings:
    print(repr(s))
print(f'Total: {len(strings)}', file=__import__('sys').stderr)
