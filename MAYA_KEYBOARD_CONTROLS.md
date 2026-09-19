# Maya keyboard controls

## Windows global shortcuts

Start `maya_hotkeys.ps1` once in a PowerShell window with:

```powershell
powershell -ExecutionPolicy Bypass -File .\maya_hotkeys.ps1
```

Then use `Ctrl+Alt+M` to wake and launch Maya, `Ctrl+Alt+W` to wake the core service only, and `Ctrl+Alt+S` to open a status window. Keep the listener running for global shortcuts. If another program already owns a combination, the listener reports that it could not register it.

## Maya window shortcuts

When Maya’s window is focused, `Ctrl+Alt+S` shows status, `Ctrl+Alt+H` shows help, `Ctrl+Alt+F` shows the weekly focus, and `Ctrl+Q` closes Maya safely. `Ctrl+Alt+Esc` remains the emergency stop and is intentionally separate from ordinary controls.

The current implementation is Windows-first because Maya currently runs through Windows and WSL2. A future macOS/Linux launcher can expose the same logical actions using each platform’s native hotkey service. Voice startup should call the same fixed launch action and should still require clear activation and confirmation for privileged actions.
