
If you are adding jupyter to a pixi env, there are two main methods that depend on
whether or not you are using the same copy of python for both jupyterlab (the shell)
and the notebooks, or different ones.


## Use same copy of python

This is for when you are launching jupyterlab from your local pixi project.

I have it setup in a "jupyter" environment within the pixi project.

```toml
[environments]
default = { features = [], solve-group = "main" }
...
jupyter = { features = ["jupyter"], solve-group = "main" }

[feature.jupyter.dependencies]
jupyterlab = ">=4.6.6,<5"
ipykernel = ">=7.4.0,<8"
nbformat = ">=5.11.1,<6"
ipywidgets = ">=8.1.9,<9"
...

[feature.jupyter.pypi-dependencies]
jupyterlab-execute-time = ">=3.3.0, <4"

```

### to launch it...
```toml
[feature.jupyter.tasks]
lab = "python jupyter/.jupyter/launcher.py"
```

This is the method I'm currently using so I can keep `jupyterlab` and this project
completely self-contained.

### see..
- `jupyter/.jupyter/launcher.py`
- `jupyter/.jupyter/jupyter_lab_config.py`
- `jupyter/.jupyter/setup.md`
 



## Using different versions of python

> I don't use this method anymore

This is most common if you want to:
- running a global install of jupyterlab -- that is, a copy of jupyterlab that is
  launched using, for example, the system's python at `/usr/bin/python`, and...
- use the copy of python currently setup in a pixi project for the actual notebooks

You would do this if you want to have a global copy of jupyterlab with all of its 
settings, all configured, etc...that you use across different projects.

In this case, I believe you would install all of your jupyterlab dependencies 
directly into the global environment, specifically including:
```
jupyterlab
pixi-kernel
ipykernel
nbformat #verify
jupyterlab-execute-time
```

This should let you pick a local pixi kernel.

### to launch it...

When I installed it globally, it used the command: `jupyter-lab`

I'm pretty sure `pixi-kernel` makes it possible to use a `pixi-kernel` based on 
whatever pixi project owns the `--notebook-dir` you use to start `jupyterlab`

see: `scripts/jupyter-global.sh` (if it exists)


### notes

I think it is possible to use `pixi-kernel` from within a pixi project, allowing you 
to use different pixi "environments" for different notebooks. I didn't need this 
functionality, so I never tested this.




