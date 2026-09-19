from pathlib import Path

root = Path(__file__).parent
app = (root / 'maya_app.py').read_text(encoding='utf-8')
hotkeys = (root / 'maya_hotkeys.ps1').read_text(encoding='utf-8')
docs = (root / 'MAYA_KEYBOARD_CONTROLS.md').read_text(encoding='utf-8')

for binding in ('<Control-Alt-s>', '<Control-Alt-h>', '<Control-Alt-f>', '<Control-q>', '<Control-Alt-Escape>'):
    assert binding in app, binding
for text in ('Ctrl+Alt+M', 'Ctrl+Alt+W', 'Ctrl+Alt+S'):
    assert text in hotkeys or text in docs, text
assert 'RegisterHotKey' in hotkeys
assert 'emergency stop' in docs.lower()
print('keyboard_controls=OK')
print('emergency_stop_separation=OK')
