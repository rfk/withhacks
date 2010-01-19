#
#  This is the dexml setuptools script.
#  Originally developed by Ryan Kelly, 2009.
#
#  This script is placed in the public domain.
#

from distutils.core import setup

import withrestart
VERSION = withrestart.__version__

NAME = "withrestart"
DESCRIPTION = "a Pythonisation of the restart-based condition system from Common Lisp"
LONG_DESC = withrestart.__doc__
AUTHOR = "Ryan Kelly"
AUTHOR_EMAIL = "ryan@rfk.id.au"
URL = "http://github.com/rfk/withrestart"
LICENSE = "MIT"
KEYWORDS = "condition restart error exception"

setup(name=NAME,
      version=VERSION,
      author=AUTHOR,
      author_email=AUTHOR_EMAIL,
      url=URL,
      description=DESCRIPTION,
      long_description=LONG_DESC,
      license=LICENSE,
      keywords=KEYWORDS,
      packages=["withrestart","withrestart.tests"],
     )

