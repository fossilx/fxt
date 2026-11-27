---
project: examples/p00_smoke
status: template
data: runs/examples/p00_smoke/
---

# examples/p00_smoke

**Question:** does the research layout work end to end?

**Hypothesis / expected result:** `pixi run research list` shows this project, `init` creates
`runs/examples/p00_smoke/{data/lake,data/scratch,artifacts}` and `runs/examples/common/data/{lake,features}`, and the notebook imports `PROJECT` from the kernel.

**Status:** template. Copy this directory to start a real project; rename the directory, then
update this README. `PROJECT` picks up the new slugs on its own.

## Log

- 2026-11-27: created as the template project.
