
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
        with xargs(func) as v:
             a = 1
             b = 2
             c = 3
        self.assertEquals(v,1*2*3)
        with xargs(func,7) as v:
             x = 8
             y = 9
        self.assertEquals(v,7*8*9)
        with xargs(func,7) as v:
             b = 8
        self.assertEquals(v,7*8*42)

    def test_xkwargs(self):
        def func(a,b,c=42):
            return a*a - b + c
        with xkwargs(func) as v:
             a = 1
             b = 2
             c = 3
        self.assertEquals(v,1*1 - 2 + 3)
        with xkwargs(func,b=2) as v:
             c = 4
             a = -1
        self.assertEquals(v,1*1 - 2 + 4)
        with xkwargs(func,b=2) as v:
             c = 3
             a = 1
             c = 5
        self.assertEquals(v,1*1 - 2 + 5)


class TestNamespace(unittest.TestCase):

    def test_namespace(self):
        a = 42
        with namespace() as ns:
            a = 2*a
        self.assertEquals(ns.a,42*2)
        with namespace() as ns:
            a = 7
            b = a * 4
            v = ValueError
        self.assertEquals(ns.b,7*4)
        self.assertEquals(ns.v,ValueError)
        b = withhacks._Bucket()
        with namespace(b):
            def hello():
                return "hi there"
            def howzitgoin():
                return "fine thanks"
        self.assertEquals(b.hello(),"hi there")
        self.assertEquals(b.howzitgoin(),"fine thanks")
        with namespace(b):
            del hello
        self.assertRaises(AttributeError,getattr,b,"hello")
        self.assertEquals(b.howzitgoin(),"fine thanks")

    def test_keyspace(self):
        a = 42
        with keyspace() as d:
            a = 2*a
        self.assertEquals(d["a"],42*2)
        with keyspace() as d:
            a = 7
            b = a * 4
            v = ValueError
        self.assertEquals(d["b"],7*4)
        self.assertEquals(d["v"],ValueError)
        d = {}
        with keyspace(d):
            def hello():
                return "hi there"
            def howzitgoin():
                return "fine thanks"
        self.assertEquals(d["hello"](),"hi there")
        self.assertEquals(d["howzitgoin"](),"fine thanks")
        with keyspace(d):
            del hello
        self.assertRaises(KeyError,d.__getitem__,"hello")
        self.assertEquals(d["howzitgoin"](),"fine thanks")


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

