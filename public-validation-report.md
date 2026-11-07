# PyMC #8467 — retained hosted Docker results

Conflict resolution: explicit `pm.Data(dtype=...)` support; upstream conversion documentation preserved.
Tested tree: `ecc01e037f5aaad58df1407edeab5aad2e2cb792`
Merged patch SHA256: `4737f5d182bfe4c7fd29ca1b497fad8f032772037a11b4c74b6e8aaf8158dbe8`
Upstream: `976ef22c5ecc89540880375d27fb879a9bfc19e1`
Run: [42322226905](https://github.com/leninworld/pymc/actions/runs/42322226905)

| floatX | Upstream `976ef22c` | Merged candidate | Added cases |
| --- | --- | --- | --- |
| float64 | 220 passed, 13 failed, 2 skipped | 228 passed, same 13 failed, 2 skipped | 8/8 pass |
| float32 | 208 passed, 25 failed, 2 skipped | 216 passed, same 25 failed, 2 skipped | 8/8 pass |

All three affected test files ran in each mode. No new failures, skips or lost cases; every
candidate failure has the same test ID on upstream.

Pre-existing failures on both revisions:
- 12 tests need Matplotlib, which `requirements-dev.txt` does not install. These include the
  sampling tests that call `set_data`, so that path was not exercised here.
- `test_get_data` needs network access, which the isolated test container did not have.
- float32 only: 12 dtype/downcast and printed-output assertions.

Pre-commit (current hooks) passes on the five changed files with no rewrites. `scripts/run_mypy.py`
exits 0 with byte-identical output on both revisions.
Python 3.12.13, PyTensor 3.3.7, NumPy 2.5.4, pandas 3.1.1, SciPy 1.18.1; PyMC reports `0+unknown`
for both archive-based revisions. All four containers stopped without OOM (peak ≈1.9 GiB).
No full-repository, Sphinx, other-OS or wheel-install validation was run. This page summarizes
retained results; it is not a fresh terminal execution.
