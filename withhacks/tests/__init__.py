
from __future__ import with_statement

import os
import sys
import unittest
import doctest

import withhacks
from withhacks import *


class TestXArgs(unittest.TestCase):

    def test_xargs(self):
        def func(a,b,c=42):
            return a * b * c
        with xargs(func) as v1:
             a = 1
             b = 2
             c = 3
        self.assertEquals(v1,1*2*3)
        with xargs(func,7) as v2:
             x = 8
             y = 9
        self.assertEquals(v2,7*8*9)
        with xargs(func,7) as v3:
             b = 8
        self.assertEquals(v3,7*8*42)


class TestMisc(unittest.TestCase):

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

