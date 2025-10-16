# Building Documentation

A basic python environment with packages listed in `./requirements.txt` is
required to build the docs, see ``environment.yml``.

To make HTML documentation:

```bash
make html
```

Outputs to `build/html/index.html`

Prose should be added in the source/ directory in one or more .rst files using
reStructuredText markup, and these files should all be referenced in the main
index.rst file, which corresponds to the documentation front page.

Any associated images should be put in the source/img/ directory.
