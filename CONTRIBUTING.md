# Contributing

sam is an internal package being developed by Ynformed. For any new code, code review by another Ynformed is therefore required!

## Bug Reports and Feature Requests

The single most important contribution that you can make is to report bugs and make feature requests. The development work on sam is largely driven by these, so please make your voice heard! Any bugs/feature requests [can be created here.](https://dev.ynformed.nl/project/view/22/) No permission is needed to create a card, so go nuts!

Bug reports are most helpful if you send us a script which reproduces the problem.

## Developing

If you want to develop this package, you wil need to install a local version using pip. This is done by going to the root folder of this package, and running `pip install -e .` This will install a development version of the package locally. That means that if you make local changes, the package will automatically reflect them. 

If you want to develop in a Jupyter notebook, you will also need to reload the sam package whenever you run `from sam import x`. This can be achieved by putting the following lines at the top of every notebook:

```
lang=python
%load_ext autoreload
%autoreload 2
```

This will reload sam everytime you run a new cell. For more information abut the autoreload extension, [see the documentation here](https://ipython.org/ipython-doc/3/config/extensions/autoreload.html)

## Linting

Linting is done automatically by arcanist before a diff. To do this, first install the dependencies

```
lang=bash
pip install pycodestyle
```

Then, to run the linter manually, go to the root folder of the project, and run `pycodestyle`. Alternatively, you can use flake8, but satisfying all flake8 rules is not required when developing this package.

## Testing

Unit tests are ran automatically by arcanist before a diff. To do this, first install the dependencies

```
lang=bash
pip install pytest
pip install pytest-cov
pip install pytest-mpl
```

Additionally, you will have to install the PytestMPLTestEngine extension. Download the file from `https://dev.ynformed.nl/P8`, and copy it to `%ARCANIST_DIR%/src/extensions/PytestMPLTestEngine.php`. Then, to run the tests manually, go the the root folder of the project, and run `arc unit`. If any of the visualizations were changed, the baseline images have to be rebuilt. This can be done with: `pytest --mpl-generate-path=sam/visualization/tests/baseline`.

## Documentation

This documentation is built automatically after every commit [by jenkins here](http://10.2.0.20/sam), with no interaction required. If you want to build it yourself locally, first install the dependencies:

```
lang=bash
pip install sphinx
pip install sphinx_rtd_theme
pip install numpydoc
pip install recommonmark
pip install sphinx-markdown-tables
```

Then, go to the /docs folder, and run the command: `sphinx-build -b html source/ build/`