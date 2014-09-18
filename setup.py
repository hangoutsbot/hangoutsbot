#!/usr/bin/env python

from distutils.core import setup
from hangupsbot.hangupsbot import __version__

setup(name='HangupsBot',
      version=__version__,
      description='Bot for Google Hangouts',
      author='Michal Krenek (Mikos)',
      author_email='m.krenek@gmail.com',
      url='https://github.com/xmikos/hangupsbot',
      license="GNU GPLv3",
      packages=['hangupsbot'],
      package_data={"hangupsbot": ["config.json"]},
      scripts=["scripts/hangupsbot"],
      requires=["hangups", "appdirs", "tornado"])
