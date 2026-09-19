import json
import tempfile
from pathlib import Path

import maya_report_export
from maya_chat import maya_local_command


def main():
    with tempfile.TemporaryDirectory() as temp:
        old_dir = maya_report_export.REPORT_DIR
        try:
            maya_report_export.REPORT_DIR = Path(temp)
            result = maya_local_command(":export week")
            assert "Week 1" in result
            assert (Path(temp) / "Week 1.docx").exists()
            print(json.dumps({"status": "ok", "router_export_command": True, "week_1_created": True}))
        finally:
            maya_report_export.REPORT_DIR = old_dir


if __name__ == "__main__":
    main()
