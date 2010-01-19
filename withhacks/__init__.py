"""

  withhacks:  building blocks for hacks using the "with" statement

http://code.google.com/p/ouspg/wiki/AnonymousBlocksInPython

"""

import sys
import new
import copy
from dis import HAVE_ARGUMENT

from withhacks.byteplay import *


class _ExitContext(Exception):
    """Special exception used to skip execution of a with-statement block."""
    pass


class WithHack(object):
    """Base class for with-statement-related hacks.

    This class provides some useful utilities for constructing with-statement
    hacks.  Specifically:

        * ability to skip execution of the contained block of code
        * ability to access the frame of execution containing the block
        * ability to update local variables in the execution frame

    """

    dont_execute = False
    must_execute = False

    def __init__(self):
        self.__trace_level = 0

    def _enable_sys_trace(self):
        """Enable function tracing at the system level.

        You must call this method before attempting any trace-function-related
        hacks, or the trace function might not actually get called.
        """
        if self.__trace_level == 0:
            try:
                self.__orig_sys_trace = sys.gettrace()
            except AttributeError:
                self.__orig_sys_trace = None
            if self.__orig_sys_trace is None:
                sys.settrace(lambda *args,**kwds: None)
        self.__trace_level += 1

    def _disable_sys_trace(self):
        """Disable function tracing at the system level."""
        self.__trace_level -= 1
        if self.__trace_level == 0:
            if self.__orig_sys_trace is None:
                sys.settrace(None)

    def _get_context_frame(self,offset=0):
        """Get the frame object corresponding to the with-statement context.

        This is designed to work from within superclass method calls, but the
        heuristics aren't 100% accurate.  You'll need to obey the following
        rules:

            * always name the self argument "self"
            * only call super() methods from within the overridden method
        
        """
        try:
            return self.__frame
        except AttributeError:
            f = sys._getframe(1+offset)
            name = f.f_code.co_name
            while f.f_locals.get("self") is self and f.f_code.co_name == name:
                f = f.f_back
            self.__frame = f
            return f

    def _set_context_locals(self,locals):
        """Set local variables in the with-statement context.

        The argument "locals" is a dictionary of name bindings to be inserted
        into the execution context of the with-statement.
        """
        frame = self._get_context_frame(1)
        def trace(frame,event,arg):
            frame.f_locals.update(locals)
            self._disable_sys_trace()
            del frame.f_trace
        self._enable_sys_trace()
        frame.f_trace = trace

    def __enter__(self):
        #  Use trace function magic to avoid executing the block if necessary
        if self.dont_execute and not self.must_execute:
            frame = self._get_context_frame()
            self.__orig_frame_trace = frame.f_trace
            self._enable_sys_trace()
            frame.f_trace = self.__exit_context_trace
        return self

    def __exit_context_trace(self,frame,event,arg):
        raise _ExitContext

    def __exit__(self,exc_type,exc_value,traceback):
        #  Restore trace function if we mucked with it
        if self.dont_execute and not self.must_execute:
            self._disable_sys_trace()
            self.__frame.f_trace = self.__orig_frame_trace
        #  Suppress the special _ExitContext exception
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
        offset = 0
        i = 0
        while i < self.__bc_start:
            offset += 1
            if code[i] >= HAVE_ARGUMENT:
                i += 2
            else:
                i += 1
        bytecode.code = bytecode.code[offset:]
        #  Remove code setting up the with-statement block.
        while bytecode.code[0][0] != SETUP_FINALLY:
            bytecode.code = bytecode.code[1:]
        bytecode.code = bytecode.code[1:]
        #  If the with-statement has an "as" clause, capture the name
        #  and remove the setup code.
        if bytecode.code[0][0] == LOAD_FAST:
            if bytecode.code[0][1].startswith("_["):
                bytecode.code = bytecode.code[2:]
            self.as_name = bytecode.code[0][1]
            bytecode.code = bytecode.code[1:]
        #  Remove code tearing down the with-statement block
        while bytecode.code[-1][0] != POP_BLOCK:
            bytecode.code = bytecode.code[:-1]
        bytecode.code = bytecode.code[:-1]
        #  Get rid of SetLineno operations, they're troublesome
        bytecode.code = [(op,arg) for (op,arg) in bytecode.code if op is not SetLineno]
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

        >>>  with CaptureFunction(("message","times",)) as f:
        ...      for i in xrange(times):
        ...          print message
        ... 
        >>>  f.function("hello world",2)
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
        #  Ensure it's properly formed by always returning something
        funcode.code.append((LOAD_CONST,None))
        funcode.code.append((RETURN_VALUE,None))
        #  Switch name access opcodes as appropriate
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
        ...     def test():
        ...         return 8
        ...
        >>> f.locals
        {'test': 8, 'x': 7}
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

        >>> with CaptureOrderdLocals() as f:
        ...     x = 7
        ...     def test():
        ...         return 8
        ...
        >>> f.locals
        [('x',7), ('test',8)]
        >>>

    """

    must_execute = True

    def __exit__(self,*args):
        retcode = super(CaptureOrderedLocals,self).__exit__(*args)
        frame = self._get_context_frame()
        local_names = []
        for (op,arg) in self.bytecode.code:
           if op == STORE_FAST:
               if arg not in local_names:
                   local_names.append(arg)
        self.locals = [(nm,frame.f_locals[nm]) for nm in local_names]
        return retcode


class extra_kwargs(CaptureLocals,CaptureBytecode):
    """WithHack calling a function with extra keyword arguments.

    This WithHack captures any local variables created during execution of
    the block, then calls the given function using them as extra keyword
    arguments.

    """

    def __init__(self,func,*args,**kwds):
        self.__func = func
        self.__args = args
        self.__kwds = kwds
        super(extra_kwargs,self).__init__()

    def __exit__(self,*args):
        retcode = super(extra_kwargs,self).__exit__(*args)
        kwds = self.__kwds.copy()
        kwds.update(self.locals)
        retval = self.__func(*self.__args,**kwds)
        if self.as_name is not None:
            self._set_context_locals({self.as_name:retval})
        return retcode


class extra_args(CaptureOrderedLocals):

    def __init__(self,func,*args,**kwds):
        self.__func = func
        self.__args = args
        self.__kwds = kwds
        super(extra_args,self).__init__()

    def __exit__(self,*args):
        retcode = super(extra_args,self).__exit__(*args)
        args_ = [arg for arg in self.__args]
        args_.extend([arg for (nm,arg) in self.locals])
        retval = self.__func(*args_,**self.__kwds)
        if self.as_name is not None:
            self._set_context_locals({self.as_name:retval})
        return retcode

