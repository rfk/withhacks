"""

  withhacks.tracefunc:  utilities for injecting frame trace functions.

"""

from __future__ import with_statement

import sys
try:
    import threading
except ImportError:
    import dummy_threading as threading


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

