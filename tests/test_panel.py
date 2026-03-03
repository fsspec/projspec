import projspec
from projspec.config import temp_conf


def test_panel_ipynb(tmpdir):
    with open(f"{tmpdir}/panel.ipynb", "wt") as f:
        f.write(test_data)
    with temp_conf(scan_types=[".ipynb"]):
        proj = projspec.Project(str(tmpdir))
        assert "panel" in proj


test_data = r"""{
 "cells": [
  {
   "cell_type": "code",
   "execution_count": null,
   "id": "b2acb5e8-c125-4d3d-b4eb-4088e1eac86a",
   "metadata": {},
   "outputs": [],
   "source": [
    "import panel as pn\n",
    "\n",
    "pn.extension()\n",
    "\n",
    "pn.panel(\"Hello World\").servable()"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3 (ipykernel)",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "codemirror_mode": {
    "name": "ipython",
    "version": 3
   },
   "file_extension": ".py",
   "mimetype": "text/x-python",
   "name": "python",
   "nbconvert_exporter": "python",
   "pygments_lexer": "ipython3",
   "version": "3.12.11"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 5
}"""
