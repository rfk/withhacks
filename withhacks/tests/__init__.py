
from __future__ import with_statement

import os
import sys
import unittest
import doctest

import withhacks
from withhacks import *


class TestWithHacks(unittest.TestCase):
    """Testcases for the "withhacks" module."""

    def test_docstrings(self):
        """Test withhacks docstrings."""
        assert doctest.testmod(withhacks)[0] == 0

    def test_README(self):
        """Ensure that the README is in sync with the docstring.

        This test should always pass; if the README is out of sync it just
        updates it with the contents of withhacks.__doc__.
        """
        dirname = os.path.dirname
        readme = os.path.join(dirname(dirname(dirname(__file__))),"README.txt")
        if not os.path.isfile(readme):
            f = open(readme,"wb")
            f.write(withhacks.__doc__)
            f.close()
        else:
            f = open(readme,"rb")
            if f.read() != withhacks.__doc__:
                f.close()
                f = open(readme,"wb")
                f.write(withhacks.__doc__)
                f.close()

