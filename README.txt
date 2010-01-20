

  withhacks:  building blocks for with-statement-related hackery

This module is a collection of useful building-blocks for hacking the Python
"with" statement.  It combines ideas from several neat with-statement hacks 
I found around the internet into a suite of re-usable components:

  * http://www.mechanicalcat.net/richard/log/Python/Something_I_m_working_on.3
  * http://billmill.org/multi_line_lambdas.html
  * http://code.google.com/p/ouspg/wiki/AnonymousBlocksInPython

By subclassing the appropriate context managers from this module, you can
easily do things such as:

  * skip execution of the code inside the with-statement
  * set local variables in the frame executing the with-statement
  * capture the bytecode from inside the with-statement
  * capture local variables defined inside the with-statement

Building on these basic tools, this module also provides some useful prebuilt
hacks:

  :xargs:      call a function with additional arguments defined in the
               body of the with-statement
  :xkwargs:    call a function with additional keyword arguments defined
               in the body of the with-statement
  :namespace:  direct all variable accesses and assignments to the attributes
               of a given object (like "with" in JavaScript or VB)
  :keyspace:   direct all variable accesses and assignments to the keys of
               of a given object (like namespace() but for dicts)

WithHacks makes extensive use of Noam Raphael's fantastic "byteplay" module;
since the official byteplay distribution doesn't support Python 2.6, a local
version with appropriate patches is included in this module.

