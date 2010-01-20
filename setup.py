#
#  This is the withhacks setuptools script.
#  Originally developed by Ryan Kelly, 2009.
#
#  This script is placed in the public domain.
#

from distutils.core import setup

import withhacks
VERSION = withhacks.__version__

NAME = "withhacks"
DESCRIPTION = "building blocks for with-statement-related hackery"
LONG_DESC = withhacks.__doc__
AUTHOR = "Ryan Kelly"
AUTHOR_EMAIL = "ryan@rfk.id.au"
URL = "http://github.com/rfk/withhacks"
LICENSE = "MIT"
KEYWORDS = "context manager with statement"

setup(name=NAME,
      version=VERSION,
      author=AUTHOR,
      author_email=AUTHOR_EMAIL,
      url=URL,
      description=DESCRIPTION,
      long_description=LONG_DESC,
      license=LICENSE,
      keywords=KEYWORDS,
      packages=["withhacks","withhacks.tests"],
     )

