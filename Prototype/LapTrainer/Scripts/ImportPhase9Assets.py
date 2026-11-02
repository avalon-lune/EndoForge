"""Explicit editor entry point for Phase9 import and actual-buffer diagnostics.

ImportPhase9Assets.ps1 supplies a fresh LAP_PHASE9_IMPORT_REPORT_DIR. This helper
does not build the editor or start an interactive/native validation sequence.
"""
import gc
import json
import os
from pathlib import Path
import runpy
import traceback

import unreal


def main():
    scripts = Path(__file__).resolve().parent
    root = scripts.parents[2]
    report = Path(os.environ["LAP_PHASE9_IMPORT_REPORT_DIR"]).resolve()
    if not report.is_relative_to((root / "tmp/phase9").resolve()):
        raise RuntimeError("Import diagnostic output must remain under tmp/phase9")
    try:
        runpy.run_path(str(scripts / "GeneratePhase9Assets.py"), run_name="__main__")
        runpy.run_path(str(scripts / "VerifyPhase9StaticAssets.py"), run_name="__main__")
        unreal.log("PHASE9_IMPORT_AND_VERIFY_PASS")
    except Exception:
        report.mkdir(parents=True, exist_ok=True)
        (report / "import-error.json").write_text(json.dumps({
            "schema": "endoforge.phase9.import-error.v1", "phase": 9,
            "diagnostic_only": True, "error": traceback.format_exc(),
        }, indent=2), encoding="utf8")
        unreal.log_error("PHASE9_IMPORT_AND_VERIFY_FAILED")
        raise
    finally:
        gc.collect()
        unreal.SystemLibrary.quit_editor()


if __name__ == "__main__":
    main()
