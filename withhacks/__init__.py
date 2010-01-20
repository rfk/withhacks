"""

  withhacks:  building blocks for with-statement-related hackery


Building on ideas from:
    http://code.google.com/p/ouspg/wiki/AnonymousBlocksInPython

"""

from __future__ import with_statement

import sys
import new
import copy
from dis import HAVE_ARGUMENT
try:
    import threading
except ImportError:
    import dummy_threading as threading

from withhacks.byteplay import *


class _ExitContext(Exception):
    """Special exception used to skip execution of a with-statement block."""
    pass


class _Bucket:
    """Anonymous attribute bucket class."""
    pass


class TraceManager(object):
    """Single class for managing frame trace functions."""

    lock = threading.Lock()
    orig_sys_trace = None
    orig_trace_funcs = {}

    @classmethod
    def _enable_tracing(self):
        """Enable system-wide tracing, if it wasn't already."""
        if len(self.orig_trace_funcs) == 1:
            try:
                self.orig_sys_trace = sys.gettrace()
            except AttributeError:
                self.orig_sys_trace = None
            if self.orig_sys_trace is None:
                sys.settrace(lambda *args,**kwds: None)

    @classmethod
    def _disable_tracing(self):
        """Disable system-wide tracing, if we specifically switched it on."""
        if len(self.orig_trace_funcs) == 1:
            if self.orig_sys_trace is None:
                sys.settrace(None)

    @classmethod
    def set_trace(self,frame,trace):
        """Set a new trace function on the given frame."""
        with self.lock:
            self.orig_trace_funcs[frame] = frame.f_trace
            frame.f_trace = trace
            self._enable_tracing()
          

    @classmethod
    def restore_trace(self,frame):
        """Restore the original trace function to the given frame."""
        with self.lock:
            self._disable_tracing()
            frame.f_trace = self.orig_trace_funcs.pop(frame)



class WithHack(object):
    """Base class for with-statement-related hackery.

    This class provides some useful utilities for constructing with-statement
    hacks.  Specifically:

        * ability to skip execution of the contained block of code
        * ability to access the frame of execution containing the block
        * ability to update local variables in the execution frame

    If a subclass sets the attribute "dont_execute" to true then execution
    of the with-statement's contained code block will be skipped.  If it sets
    the attribute "must_execute" to true, the block will be executed regardless
    of the setting of "dont_execute".  Having two settings allows hacks that
    want to skip the block to be combined with hacks that need it executed.
    """

    dont_execute = False
    must_execute = False

    def _get_context_frame(self):
        """Get the frame object corresponding to the with-statement context.

        This is designed to work from within superclass method call. It finds
        the first frame in which the variable "self" is not bound to this 
        object.  While this heuristic rules out some strange uses of WithHack
        objects (such as entering on object inside its own __exit__ method)
        it should suffice in practise.
        """
        try:
            return self.__frame
        except AttributeError:
            # Offset 2 accounts for this method, and the one calling it.
            f = sys._getframe(2)
            while f.f_locals.get("self") is self:
                f = f.f_back
            self.__frame = f
            return f

    def _set_context_locals(self,locals):
        """Set local variables in the with-statement context.

        The argument "locals" is a dictionary of name bindings to be inserted
        into the execution context of the with-statement.
        """
        frame = self._get_context_frame()
        def trace(frame,event,arg):
            frame.f_locals.update(locals)
            TraceManager.restore_trace(frame)
        TraceManager.set_trace(frame,trace)

    def __enter__(self):
        if self.dont_execute and not self.must_execute:
            frame = self._get_context_frame()
            def trace(frame,event,arg):
                raise _ExitContext
            TraceManager.set_trace(frame,trace)
        return self

    def __exit__(self,exc_type,exc_value,traceback):
        if self.dont_execute and not self.must_execute:
            TraceManager.restore_trace(self._get_context_frame())
        if exc_type is _ExitContext:
            return True
        else:
            return False


class CaptureBytecode(WithHack):
    """WithHack to capture the bytecode in the scope of a with-statement.

    The captured bytecode is stored as a byteplay.Code object in the attribute
    "bytecode".  Note that there's no guarantee that this sequence of bytecode
    can be turned into a valid code object!  For example, it may not properly
    return a value.

    If the with-statement contains an "as" clause, the name of the variable
    is stored in the attribute "as_name".
    """

    dont_execute = True

    def __init__(self):
        self.__bc_start = None
        self.bytecode = None
        self.as_name = None
        super(CaptureBytecode,self).__init__()

    def __enter__(self):
        self.__bc_start = self._get_context_frame().f_lasti
        return super(CaptureBytecode,self).__enter__()

    def __exit__(self,*args):
        frame = self._get_context_frame()
        code = frame.f_code.co_code
        bytecode = Code.from_code(frame.f_code)
        offset_start = -1
        i = 0
        while i < self.__bc_start:
            offset_start += 1
            if code[i] >= HAVE_ARGUMENT:
                i += 2
            else:
                i += 1
        offset_end = offset_start
        while i < frame.f_lasti:
            offset_end += 1
            if code[i] >= HAVE_ARGUMENT:
                i += 2
            else:
                i += 1
        self.bytecode_before = copy.deepcopy(bytecode)
        self.bytecode_after = copy.deepcopy(bytecode)
        self.bytecode_before.code = bytecode.code[:offset_start]
        self.bytecode_after.code = bytecode.code[offset_end:]
        bytecode.code = bytecode.code[offset_start:offset_end]
        #  Remove code setting up the with-statement block.
        while bytecode.code[0][0] != SETUP_FINALLY:
            bytecode.code = bytecode.code[1:]
        bytecode.code = bytecode.code[1:]
        #  If the with-statement has an "as" clause, capture the name
        #  and remove the setup code.
        if bytecode.code[0][0] in (LOAD_FAST,LOAD_NAME,LOAD_DEREF,LOAD_GLOBAL):
            if bytecode.code[0][1].startswith("_["):
                bytecode.code = bytecode.code[2:]
            self.as_name = bytecode.code[0][1]
            bytecode.code = bytecode.code[1:]
        #  Remove code tearing down the with-statement block
        while bytecode.code[-1][0] != POP_BLOCK:
            bytecode.code = bytecode.code[:-1]
        bytecode.code = bytecode.code[:-1]
        #  OK, ready!
        self.bytecode = bytecode
        return super(CaptureBytecode,self).__exit__(*args)


class CaptureFunction(CaptureBytecode):
    """WithHack to capture contents of with-statement as anonymous function.

    The bytecode of the contained block is converted into a function and
    made available as the attribute "function".  The following arguments
    control the signature of the function:

        * args:       tuple of argument names
        * varargs:    boolean indicating present of a *args argument
        * varkwargs:  boolean indicating present of a *kwargs argument
        * name:       name associated with the function object
        * argdefs:    tuple of default values for arguments

    Here's a quick example:

        >>> with CaptureFunction(("message","times",)) as f:
        ...     for i in xrange(times):
        ...         print message
        ...
        >>> f.function("hello world",2)
        hello world
        hello world
        >>>

    """

    def __init__(self,args=[],varargs=False,varkwargs=False,name="<withhack>",
                      argdefs=()):
        self.__args = args
        self.__varargs = varargs
        self.__varkwargs = varkwargs
        self.__name = name
        self.__argdefs = argdefs
        super(CaptureFunction,self).__init__()

    def __exit__(self,*args):
        frame = self._get_context_frame()
        retcode = super(CaptureFunction,self).__exit__(*args)
        funcode = copy.deepcopy(self.bytecode)
        #  Ensure it's a properly formed func by always returning something
        funcode.code.append((LOAD_CONST,None))
        funcode.code.append((RETURN_VALUE,None))
        #  Switch name access opcodes as appropriate.
        #  Any new locals are local to the function; existing locals
        #  are manipulated using LOAD/STORE/DELETE_NAME.
        for (i,(op,arg)) in enumerate(funcode.code):
            if op in (LOAD_FAST,LOAD_DEREF,LOAD_NAME,LOAD_GLOBAL):
                if arg in self.__args:
                    op = LOAD_FAST
                elif op in (LOAD_FAST,LOAD_DEREF,):
                    if arg in frame.f_locals:
                        op = LOAD_NAME
                    else:
                        op = LOAD_FAST
            elif op in (STORE_FAST,STORE_DEREF,STORE_NAME,STORE_GLOBAL):
                if arg in self.__args:
                    op = STORE_FAST
                elif op in (STORE_FAST,STORE_DEREF,):
                    if arg in frame.f_locals:
                        op = STORE_NAME
                    else:
                        op = STORE_FAST
            elif op in (DELETE_FAST,DELETE_NAME,DELETE_GLOBAL):
                if arg in self.__args:
                    op = DELETE_FAST
                elif op in (DELETE_FAST,):
                    if arg in frame.f_locals:
                        op = DELETE_NAME
                    else:
                        op = DELETE_FAST
            funcode.code[i] = (op,arg)
        #  Create the resulting function object
        funcode.args = self.__args
        funcode.varargs = self.__varargs
        funcode.varkwargs = self.__varkwargs
        funcode.name = self.__name
        gs = self._get_context_frame().f_globals
        nm = self.__name
        defs = self.__argdefs
        self.function = new.function(funcode.to_code(),gs,nm,defs)
        return retcode


class CaptureLocals(WithHack):
    """WithHack to capture any local variables modified in the block.

    When the block exits, the attribute "locals" will be a dictionary 
    containing any local variables that were created or modified during
    the execution of the block. 

        >>> with CaptureLocals() as f:
        ...     x = 7
        ...     y = 8
        ...
        >>> f.locals
        {'y': 8, 'x': 7}
        >>>

    """

    must_execute = True

    def __enter__(self):
        frame = self._get_context_frame()
        self.__pre_locals = frame.f_locals.copy()
        return super(CaptureLocals,self).__enter__()

    def __exit__(self,*args):
        frame = self._get_context_frame()
        self.locals = {}
        for (name,value) in frame.f_locals.iteritems():
            if value is self:
                pass
            elif name not in self.__pre_locals:
                self.locals[name] = value
            elif self.__pre_locals[name] is not value:
                self.locals[name] = value
        del self.__pre_locals
        return super(CaptureLocals,self).__exit__(*args)


class CaptureOrderedLocals(CaptureBytecode):
    """WithHack to capture local variables modified in the block, in order.

    When the block exits, the attribute "locals" will be a list containing
    a (name,value) pair for each local variable created or modified during
    the execution of the block.   The variables are listed in the order
    they are first assigned.

        >>> with CaptureOrderedLocals() as f:
        ...     x = 7
        ...     y = 8
        ...
        >>> f.locals
        [('x', 7), ('y', 8)]
        >>>

    """

    must_execute = True

    def __exit__(self,*args):
        retcode = super(CaptureOrderedLocals,self).__exit__(*args)
        frame = self._get_context_frame()
        local_names = []
        for (op,arg) in self.bytecode.code:
           if op in (STORE_FAST,STORE_NAME,):
               if arg not in local_names:
                   local_names.append(arg)
        self.locals = [(nm,frame.f_locals[nm]) for nm in local_names]
        return retcode


class xargs(CaptureOrderedLocals):
    """WithHack to call a function with arguments defined in the block.

    This WithHack captures the value of any local variables created or 
    modified in the scope of the block, then passes those values as extra
    positional arguments to the given function call.  The result of the
    function call is stored in the "as" variable if given.

        >>> with xargs(filter) as evens:
        ...     def filter_func(i):
        ...         return (i % 2) == 0
        ...     items = range(10)
        ...
        >>> print evens
        [0, 2, 4, 6, 8]
        >>>
      
    """

    def __init__(self,func,*args,**kwds):
        self.__func = func
        self.__args = args
        self.__kwds = kwds
        super(xargs,self).__init__()

    def __exit__(self,*args):
        retcode = super(xargs,self).__exit__(*args)
        args_ = [arg for arg in self.__args]
        args_.extend([arg for (nm,arg) in self.locals])
        retval = self.__func(*args_,**self.__kwds)
        if self.as_name is not None:
            self._set_context_locals({self.as_name:retval})
        return retcode


class xkwargs(CaptureLocals,CaptureBytecode):
    """WithHack calling a function with extra keyword arguments.

    This WithHack captures any local variables created during execution of
    the block, then calls the given function using them as extra keyword
    arguments.

        >>> def calculate(a,b):
        ...     return a * b
        ...
        >>> with xkwargs(calculate,b=2) as result:
        ...     a = 5
        ...
        >>> print result
        10

    """

    def __init__(self,func,*args,**kwds):
        self.__func = func
        self.__args = args
        self.__kwds = kwds
        super(xkwargs,self).__init__()

    def __exit__(self,*args):
        retcode = super(xkwargs,self).__exit__(*args)
        kwds = self.__kwds.copy()
        kwds.update(self.locals)
        retval = self.__func(*self.__args,**kwds)
        if self.as_name is not None:
            self._set_context_locals({self.as_name:retval})
        return retcode


class namespace(CaptureBytecode):
    """WithHack sending assignments to a specified namespace.

    This WithHack permits a construct simlar to the "with" statement from
    Visual Basic or JavaScript.  Inside a namespace context, all local
    variable accesses are actually accesses to the attributes of that
    object.

        >>> import sys
        >>> with namespace(sys):
        ...     testing = "hello"
        ...     copyright2 = copyright
        ...
        >>> print sys.testing
        hello
        >>> print sys.copyright2 == sys.copyright
        True

    If no object is passed to the constructor, an empty object is created and
    used.  To get a reference to the namespace, use an "as" clause:

        >>> with namespace() as ns:
        ...     x = 1
        ...     y = x + 4
        ...
        >>> print ns.x; print ns.y
        1
        5

    """

    def __init__(self,ns=None):
        if ns is None:
            self.namespace = _Bucket()
        else:
            self.namespace = ns
        super(namespace,self).__init__()

    def __exit__(self,*args):
        frame = self._get_context_frame()
        retcode = super(namespace,self).__exit__(*args)
        funcode = copy.deepcopy(self.bytecode)
        #  Ensure it's a properly formed func by always returning something
        funcode.code.append((LOAD_CONST,None))
        funcode.code.append((RETURN_VALUE,None))
        #  Switch LOAD/STORE/DELETE_FAST/NAME to LOAD/STORE/DELETE_ATTR
        self._adjust_names(funcode)
        #  Create function object to do the manipulation
        funcode.args = ("namespace",)
        funcode.varargs = False
        funcode.varkwargs = False
        funcode.name = "<withhack>"
        gs = self._get_context_frame().f_globals
        func = new.function(funcode.to_code(),gs)
        #  Execute bytecode in context of namespace
        retval = func(self.namespace)
        if self.as_name is not None:
            self._set_context_locals({self.as_name:self.namespace})
        return retcode

    def _adjust_names(self,funcode):
        for (i,(op,arg)) in enumerate(funcode.code):
            if op in (LOAD_FAST,LOAD_NAME,):
                funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(LOAD_ATTR,arg)]
            elif op in (STORE_FAST,STORE_NAME,):
                funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(STORE_ATTR,arg)]
            elif op in (DELETE_FAST,DELETE_NAME,):
                funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(DELETE_ATTR,arg)]
            elif op in (LOAD_GLOBAL,LOAD_DEREF,):
                if not self._name_used_before(arg):
                    funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(LOAD_ATTR,arg)]
            elif op in (DELETE_GLOBAL,):
                if not self._name_used_before(arg):
                    funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(DELETE_ATTR,arg)]

    def _name_used_before(self,name):
        for (op,arg) in self.bytecode_before.code:
            if op in (LOAD_GLOBAL,LOAD_DEREF,STORE_GLOBAL,STORE_DEREF,):
                if arg == name:
                    return True
        return False


class keyspace(namespace):
    """WithHack sending assignments to a specified dict-like object.

    This WithHack permits a construct simlar to the "with" statement from
    Visual Basic or JavaScript.  Inside a namespace context, all local
    variable accesses are actually accesses to the keys of that object.

        >>> import sys
        >>> with keyspace(sys.__dict__):
        ...     testing = "hello"
        ...     copyright2 = copyright
        ...
        >>> print sys.testing
        hello
        >>> print sys.copyright2 == sys.copyright
        True

    If no object is passed to the constructor, an empty dict is created and
    used.  To get a reference to the keyspace, use an "as" clause:

        >>> with keyspace() as ks:
        ...     x = 1
        ...     y = x + 4
        ...
        >>> print ks["x"]; print ks["y"]
        1
        5

    """

    def __init__(self,ns=None):
        if ns is None:
            ns = {}
        super(keyspace,self).__init__(ns)

    def _adjust_names(self,funcode):
        for (i,(op,arg)) in enumerate(funcode.code):
            if op in (LOAD_FAST,LOAD_NAME,):
                funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(LOAD_CONST,arg),(BINARY_SUBSCR,None)]
            elif op in (STORE_FAST,STORE_NAME,):
                funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(LOAD_CONST,arg),(STORE_SUBSCR,None)]
            elif op in (DELETE_FAST,DELETE_NAME,):
                funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(LOAD_CONST,arg),(DELETE_SUBSCR,None)]
            elif op in (LOAD_GLOBAL,LOAD_DEREF,):
                if not self._name_used_before(arg):
                    funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(LOAD_CONST,arg),(BINARY_SUBSCR,None)]
            elif op in (DELETE_GLOBAL,):
                if not self._name_used_before(arg):
                    funcode.code[i:i+1]=[(LOAD_FAST,"namespace"),(LOAD_CONST,arg),(DELETE_SUBSCR,None)]

