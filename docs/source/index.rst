``projspec``: A common interface to code projects
=================================================

Welcome to projspec, the projects' project!

There are many ways to organise project-oriented code workflows, and projspec aims
to give a unified experience, so that you don't have to learn them all. This allows
for the following types of use-cases:

- *browsing/introspection*: a project is *shared* with you (github, gdrive, your corp's storage solution), and
  you want to know what it is and what it needs, without downloading and browsing a
  bunch of readme and scripts.
- *search*: you have access to a large number of projects on your disk or elsewhere and you want
  to find the project that meets some criteria like "it uses package X", "it needs
  dataset Y" or "it can make a conda package". The names of directories alone are not enough.
- *actions*: you want an app to launch in a single command without diving deeper. This may also
  extend to "deployment" scenarios where you want to be able to run many kinds of applications
  without building custom scripts every time.
- *summaries*: you host projects for your org, and want to know how many are affected by some given
  CVE, or how many rely on a rust compiler.

The "intro" defined this package's scope and sets some definitions. The "quickstart"
shows some of the concrete things you can actually do right now.

Introduction to projspec presented at PyData Global 2025: `video`_ | `slides`_

.. _video: https://www.youtube.com/watch?v=cZi3diO7td0&list=PLGVZCDnMOq0qmerwB1eITnr5AfYRGm0DF&index=36
.. _slides: https://docs.google.com/presentation/d/1AdQuMevqLKJeT9HSS5_4G9Jddz7NHoYUn1l6wk_a-jI/edit?usp=sharing

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   intro.rst
   quickstart.rst
   api.rst
   contributing.rst
   code-of-conduct.rst


These docs pages collect anonymous tracking data using goatcounter, and the
dashboard is available to the public: https://projspec.goatcounter.com/ .

.. raw:: html

    <script data-goatcounter="https://projspec.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
