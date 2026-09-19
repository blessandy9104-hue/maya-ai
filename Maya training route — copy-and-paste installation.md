# Maya training route — copy-and-paste installation

## Files

Keep these two files in the Maya project folder.

- `maya_training.py`
- `test_maya_training.py`

They are standalone and do not overwrite Maya's existing files.

## Verify the module

Open PowerShell and run:

```powershell
cd "C:\path\to\Maya_App_Copy"
py -3 .\test_maya_training.py
```

Expected output:

```text
maya_training_ok
```

## Supported commands after integration

```text
training example: ...
training preference: ...
training review
training approve train-XXXXXXXXXX
training reject train-XXXXXXXXXX
training edit train-XXXXXXXXXX: ...
```

## Important boundary

The module stores explicit training statements in `maya_training_state.json` as `pending_review`. It never promotes them to approved context unless `training approve <id>` is issued explicitly. It does not enable Presence Mode, browser observation, public browsing, external actions, or self-modifying code.

The standalone test can be run immediately. Wiring these commands into the running desktop router requires the latest `maya_chat.py` from the Windows project; do not replace that file until the sidecar is available or the current file has been copied for backup.
