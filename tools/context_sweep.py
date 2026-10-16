"""Play every opening cast of every world through the context budget check.

Core plays only the heaviest few casts (tests/core/test_context.py); this runs
the same test over all of them. Run it before a release:

    python tools/context_sweep.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    env = dict(os.environ, AT_CONTEXT_SWEEP="all")
    test = "test_context.FullContextBudgetTest.test_the_heaviest_casts_with_newcomers_stay_within_budget"
    return subprocess.call([sys.executable, "-m", "unittest", test], cwd=os.path.join(ROOT, "tests", "core"), env=env)


if __name__ == "__main__":
    sys.exit(main())
