"""Phase 4 collision-fix delivery; the original Phase 1–4 outputs stay read-only."""
import sys

from finalize_phase4 import main


if __name__ == "__main__":
    # Reuse every original gate and add collision evidence / four-phase preservation.
    sys.argv.insert(1, "--collision-fix")
    main()
