# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # examples/p00_smoke: n01_explore
#
# Template notebook. Paths come from `PROJECT`, never from the notebook's
# working directory, so the notebook works wherever Lab was started.

# %%
from fxtapps.research.examples.p00_smoke import PROJECT

paths = PROJECT.paths()
PROJECT.key, paths.root

# %% [markdown]
# Scratch output goes in the declared `scratch` dir; anything a result depends
# on belongs in a run (`artifacts/<run-id>/`) once run tracking exists. A
# derived dataset with the main lake's layout goes in `paths.data.lake`.

# %%
paths.ensure()
scratch = paths.data.dir("scratch")
(scratch / "hello.txt").write_text("hello from n01_explore\n")
sorted(p.name for p in scratch.iterdir()), paths.data.lake.root, paths.common.dir("features")
