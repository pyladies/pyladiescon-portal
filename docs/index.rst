==================
pyladiescon-portal
==================

About PyLadiesCon
=================

`PyLadiesCon`_ is an online conference for the global `PyLadies`_ community. Our conference began in 2023. During our conference, we host 24 hours of online engagement, talks, keynotes, panels, and workshops for our community members. We strive of inclusivity and accessibility, providing talks in multiple-languages, and we take extra care in subtitling and translating our talks. Our conference is free to attend, and attendees can optionally donate to our conference.

Being an online, multi-language, multi-timezone conference, we face unique and different challenges from other types of events and conferences. Our organizers are all volunteers from different part of the world. We have many communications and coordinations with our team of volunteers ahead of the conference, and less during the conference itself.

What we're building: PyLadiesCon Web Portal
===========================================

This year, we are developing an online web portal for us to manage the behind the scenes work of our conference. Instead of Spreadsheets, we will be accepting volunteer sign ups and sponsorship sign ups through our web portal. Our team leads will be assigning task and tracking team progress through the web portal. We also want to build a conference dashboard to provide overview and statistics about our conference.

* `Video preview`_
* `The Portal`_

Our Tech Stack
==============
Our portal is developed using `Python`_ programming language (Python 3.13) and `Django`_ web framework (v5.1.7).

In addition to Python and Django, we are using various third party libraries like `django-allauth`_, `pytest`_, `coverage`_. We can and will add other third-party libraries as the need arises.

Our web app is Dockerized, and we use Postgres as our database.

Thanks to the support from The PSF's Infrastructure team, we're able to deploy our web app using `cabotage`_, the same infrastructure that powers `PyPI`_.

For working with Git, and GitHub, we recommend using `GitHub CLI`_, but it is optional.

Our Codebase
============

* `GitHub repo`_
* `Local dev setup guide`_
* `Production deployment`_
* `Project Board`_
* `Project Milestones`_

Table of contents
=================

:ref:`How-to guides <how-to>`
-----------------------------

Guides and recipes for common problems and tasks, including how to contribute.


Community
=========

`PyLadiesCon`_  is part of the `PyLadies`_. You can talk to the community through:

* `@pyladies@fosstodon.org on Mastodon <https://fosstodon.org/@pyladies>`__

* `Discord <https://discord.gg/U3M6nPA55X>`__

* The Pyladies `Slack <https://slackin.pyladies.com/>`__

.. _PyLadiesCon: https://conference.pyladies.com/
.. _PyLadies: https://pyladies.com/
.. _Video preview: https://github.com/user-attachments/assets/facd5633-acad-4958-bd2a-36f8ae429432
.. _The Portal: https://pyladiescon-portal.us-east-2.psfhosted.computer/
.. _Python: https://python.org/
.. _Django: https://www.djangoproject.com/
.. _django-allauth: https://docs.allauth.org/en/latest/
.. _pytest: https://docs.pytest.org/en/stable/
.. _coverage: https://coverage.readthedocs.io/
.. _cabotage: https://github.com/cabotage/cabotage-app
.. _PyPI: https://pypi.org/
.. _Github CLI: https://cli.github.com/
.. _GitHub repo: https://github.com/pyladies/pyladiescon-portal
.. _Local dev setup guide: https://github.com/pyladies/pyladiescon-portal?tab=readme-ov-file#local-dev-setup
.. _Production deployment: https://pyladiescon-portal.us-east-2.psfhosted.computer/
.. _Project Board: https://github.com/orgs/pyladies/projects/11
.. _Project Milestones: https://github.com/pyladies/pyladiescon-portal/milestones
.. _Read The Docs: https://briefcase.readthedocs.io

.. toctree::
   :maxdepth: 2
   :hidden:
   :titlesonly:

   how-to/index