"""

  withhacks.frameutils:  utilities for hacking with frame objects

"""

from __future__ import with_statement

import sys
import dis
import new
try:
    import threading
except ImportError:
    import dummy_threading as threading

from withhacks.byteplay import Code


__all__ = ["inject_trace_func","extract_code","load_name"]

_trace_lock = threading.Lock()
_orig_sys_trace = None
_orig_trace_funcs = {}
_injected_trace_funcs = {}


def _dummy_sys_trace(*args,**kwds):
    """Dummy trace function used to enable tracing."""
    pass


def _enable_tracing():
    """Enable system-wide tracing, if it wasn't already."""
    global _orig_sys_trace
    try:
        _orig_sys_trace = sys.gettrace()
    except AttributeError:
        _orig_sys_trace = None
    if _orig_sys_trace is None:
        sys.settrace(_dummy_sys_trace)


def _disable_tracing():
    """Disable system-wide tracing, if we specifically switched it on."""
    global _orig_sys_trace
    if _orig_sys_trace is None:
        sys.settrace(None)


def inject_trace_func(frame,func):
    """Inject the given function as a trace function for frame.

    The given function will be executed immediately as the frame's execution
    resumes.  Since it's running inside a trace hook, it can do some nasty
    things like modify frame.f_locals, frame.f_lasti and friends.
    """
    with _trace_lock:
        if frame.f_trace is not _invoke_trace_funcs:
            _orig_trace_funcs[frame] = frame.f_trace
            frame.f_trace = _invoke_trace_funcs
            _injected_trace_funcs[frame] = []
            if len(_orig_trace_funcs) == 1:
                _enable_tracing()
    _injected_trace_funcs[frame].append(func)


def _invoke_trace_funcs(frame,*args,**kwds):
    """Invoke any trace funcs that have been injected.

    Once all injected functions have been executed, the trace hooks are
    removed.  Hopefully this will keep the overhead of all this madness
    to a minimum :-)
    """
    try:
        for func in _injected_trace_funcs[frame]:
            func(frame)
    finally:
        del _injected_trace_funcs[frame]
        with _trace_lock:
            if len(_orig_trace_funcs) == 1:
                _disable_tracing()
            frame.f_trace = _orig_trace_funcs.pop(frame)


def extract_code(frame,start=None,end=None,name="<withhack>"):
    """Extract a Code object corresponding to the given frame.

    Given a frame object, this function returns a byteplay Code object with
    containing the code being executed by the frame.  If the optional "start"
    "start" and/or "end" arguments are given, they are used as indices to
    return only a slice of the code.
    """
    code = frame.f_code
    if start is None:
        if end is None:
            code_str = code.co_code[:]
        else:
            code_str = code.co_code[:end]
    else:
        #  Slicing off opcodes at start means we need to adjust any
        #  absolute jump targets.
        if end is None:
            code_list = [c for c in code.co_code[start:]]
        else:
            code_list = [c for c in code.co_code[start:end]]
        i = 0
        while i < len(code_list):
            c = ord(code_list[i])
            if c in dis.hasjabs:
                code_list[i+1] = chr(ord(code_list[i+1]) - start)
                i += 2
            else:
                if c >= dis.HAVE_ARGUMENT:
                    i += 2
                else:
                    i += 1
        code_str = "".join(code_list)
    new_code = new.code(0, code.co_nlocals, 
                        code.co_stacksize, code.co_flags,
                        code_str, code.co_consts,
                        code.co_names, code.co_varnames,
                        code.co_filename, name,
                        frame.f_lineno, code.co_lnotab)
    return Code.from_code(new_code)


def load_name(frame,name):
    """Get the value of the named variable, as seen by the given frame.

    The name is first looked for in f_locals, then f_globals, and finally
    f_builtins.  If it's not defined in any of these scopes, NameError 
    is raised.
    """
    try:
        return frame.f_locals[name]
    except KeyError:
        try:
            return frame.f_globals[name]
        except KeyError:
            try:
                return frame.f_builtins[name]
            except KeyError:
                raise NameError(name)


