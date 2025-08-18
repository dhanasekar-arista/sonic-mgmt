from functools import wraps
import contextvars
import logging

logger = logging.getLogger(__name__)

# A context variable is created. This acts as a thread-safe global
# that holds the loganalyzer instance for the scope of a single test.
# It's defined here to avoid circular imports.
loganalyzer_context = contextvars.ContextVar('loganalyzer', default=None)


def support_ignore_loganalyzer(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        """
        try to fetch loganalyzer instances from kwargs:
        if ignore_loganalyzer is not passed, do nothing but execute the decorated function.
        if ignore_loganalyzer is passed, to avoid 'unexpected keyword argument error',
            delete the ignore_loganalyzer from kwargs so that it would not be passed to the decorated function,
            and set ignore_loganalyzer markers before and after the decorated function on all log analyzer instances.
        """

        # Need to remove parameter 'ignore_loganalyzer' from kwargs
        # Otherwise it breaks the decorated func
        # Since the parameter 'ignore_loganalyzer' is not defined in the signature
        loganalyzer = kwargs.pop('ignore_loganalyzer', {})

        if loganalyzer:
            for _, dut_loganalyzer in list(loganalyzer.items()):
                dut_loganalyzer.add_start_ignore_mark()

        try:
            res = func(*args, **kwargs)
        finally:
            if loganalyzer:
                for _, dut_loganalyzer in list(loganalyzer.items()):
                    dut_loganalyzer.add_end_ignore_mark()

        return res

    return decorated

def wrap_in_marker(func):
    """
    A decorator that wraps a command execution function to add start/end markers
    to the DUT's syslog. It automatically gets the loganalyzer from a context
    variable, which is set by a pytest fixture.
    """
    @wraps(func)
    def decorated(instance, *args, **kwargs):
        # The decorator retrieves the loganalyzer from the context.
        loganalyzer = loganalyzer_context.get()
        cmd_marker = None

        # The actual command string is expected to be the first positional arg.
        if loganalyzer and args:
            cmd_str = args[0]
            # Sanitize the command string to create a valid marker name.
            cmd_marker = cmd_str.replace(' ', '_').replace('/', '-').replace('"', '')
            try:
                # Assuming loganalyzers is a dictionary of DUTs.
                for dut in loganalyzer:
                    loganalyzer[dut].add_command_start_mark(cmd_marker)
            except TypeError:
                # Handle cases where loganalyzer is not a dictionary.
                logger.error("loganalyzer context variable is not a dictionary of DUTs.")
                cmd_marker = None

        try:
            # Execute the original function.
            result = func(instance, *args, **kwargs)
        finally:
            # This block runs even if the command above raises an exception.
            if loganalyzer and cmd_marker is not None:
                try:
                    for dut in loganalyzer:
                        loganalyzer[dut].add_command_end_mark()
                except TypeError:
                    # Handle cases where loganalyzer is not a dictionary.
                    pass

        return result

    return decorated
