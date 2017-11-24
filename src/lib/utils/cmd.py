# coding: utf-8

import subprocess as sp

from ..common.logger import *


## Class, which represent completed process.
# @description Class, which represent completed process. Its implementation same
#  as in CPython 3.5 except check_errors,
class CompletedProcess:

    ## Constructor.
    # @param args String or list of command line arguments.
    # @param returncode Code, that was returned by process.
    # @param stdout Content of standard output.
    # @param stderr Content of standard error output.
    def __init__(self, args, returncode, stdout=None, stderr=None):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    ## Debug representation of object.
    # @param self Pointer to object.
    def __repr__(self):
        args = ['args={!r}'.format(self.args),
                'returncode={!r}'.format(self.returncode)]
        if self.stdout is not None:
            args.append('stdout={!r}'.format(self.stdout.decode(gv.ENCODING)))
        if self.stderr is not None:
            args.append('stderr={!r}'.format(self.stderr.decode(gv.ENCODING)))
        return "{}({})".format(type(self).__name__, ', '.join(args))


## Simple implementation of subprocess.run from CPython 3.5.
# @param args String or list of command line arguments.
# @param shell Should args be executed in shell or not.
# @param timeout Time for process execution. If execution time exceeds timeout,
#  sp.TimeoutExpired raised.
# @return CompletedProcess object.
# @exception TimeoutExpired
def run_cmd(args, shell=False, timeout=None):
    with sp.Popen(args, stdout=sp.PIPE, stderr=sp.PIPE, shell=shell) as process:
        global_logger.debug(args=process.args, pid=process.pid)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except sp.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise sp.TimeoutExpired(process.args, timeout, output=stdout,
                                 stderr=stderr)
        except Exception as err:
            process.kill()
            process.wait()
            raise
        retcode = process.poll()
        cp = CompletedProcess(process.args, retcode, stdout, stderr)
        global_logger.debug(cp)
        return cp
