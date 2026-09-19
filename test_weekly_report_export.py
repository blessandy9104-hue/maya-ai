import json
import tempfile
import zipfile
from pathlib import Path

import maya_report_export as exporter


def main():
    with tempfile.TemporaryDirectory() as temp:
        old_dir = exporter.REPORT_DIR
        try:
            exporter.REPORT_DIR = Path(temp)
            profile = exporter.ROOT / "andy_profile.json"
            before = profile.read_bytes() if profile.exists() else None
            first = exporter.export_weekly_report("Weekly pattern report (local evidence review):\nTentative theme: testing report export.")
            second = exporter.export_weekly_report("Weekly pattern report (local evidence review):\nSecond report.")
            first_path = Path(temp) / "Week 1.docx"
            second_path = Path(temp) / "Week 2.docx"
            assert first_path.exists() and second_path.exists()
            assert "Week 1" in first and "Week 2" in second
            with zipfile.ZipFile(first_path) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
            assert "review-only" in document.lower()
            assert "Tentative theme" in document
            after = profile.read_bytes() if profile.exists() else None
            assert before == after
            print(json.dumps({"status": "ok", "week_1": True, "week_2": True, "duplicate_protection": True, "review_only_label": True, "profile_unchanged": True}))
        finally:
            exporter.REPORT_DIR = old_dir


if __name__ == "__main__":
    main()
