# coding: utf-8

import re

from .logger import *

# Compare current version of Python interpreter against minimal required
if sys.version_info < (3, 4, 3):
    raise Exception(
        "Incompatible version of Python interpreter. "
        "Minimum required version: 3.4.3"
    )

import threading
import datetime
import platform
import subprocess as sp
import shlex


## Function, which acts as custom excepthook
#
# @param exctype Exception type
# @param value Exception value
# @param traceback Exception traceback
def my_except_hook(exctype, value, traceback):
    # if keyboard interrupt came, terminate script
    if exctype is KeyboardInterrupt:
        global_logger.error(
            "Keyboard interrupt", pid=os.getpid(),
            test_mode=gv.TEST_MODE,
            err_code=-1
        )
        os._exit(1)
    else:
        sys.__excepthook__(exctype, value, traceback)


sys.excepthook = my_except_hook


## Detect encoding of default shell.
#
# @return String, which represent encoding. If decoding cannot be detected,
#  "raw_unicode_escape" returns.
def detect_console_encoding():
    encoding = "raw_unicode_escape"
    system = platform.system()
    try:
        # if system is Windows, then detect via chcp
        if system == "Windows":
            popen = sp.Popen(
                "chcp",
                shell=True,
                stdout=sp.PIPE,
                stderr=sp.PIPE)
            stdout, _ = popen.communicate(timeout=2)
            encoding = re.search(b" ([a-zA-Z0-9_\\-]+)", stdout).groups()[0]\
                .decode(gv.ENCODING)
        # if Linux, then set utf-8
        elif system == "Linux":
            encoding = "utf-8"
        test = "trying encode string".encode(encoding)
        return encoding
    except Exception as err:
        return "raw_unicode_escape"


from .logger import *
from .errors import *
from ..utils.cvt import str_to_bool


## Set global lib::common::global_vars::ENCODING variable.
gv.ENCODING = detect_console_encoding()


## Default function for second argument in parse_cmd_args.
def set_debug_values(args):
    for key, value in args.items():
        if key.lower() in ["debug", "collapse-traceback", "print-begin",
                              "print-uuid", "print-function", "escape-strings"]:
            try:
                setattr(gv, key.upper().replace("-", "_"),
                        value)
            except ValueError:
                raise AutomationLibraryError("ARGS_ERROR",
                                             "This arg should be True or False",
                                             key=key, current_value=value)


## Parse input command line arguments (from sys.argv) an return tuple with
#  (positional_args, named_args).
# @param s Input list or string. If None, then args retrieved from sys.argv[2:].
#  If string, then args splitted via shlex.
# @return Tuple with (positional_args, named_args), where positional_args
#  is list of args and named_args is dict.
def parse_cmd_args(s=None):
    args = ([], {})
    if s is None:
        s = sys.argv
    elif isinstance(s, list):
        pass
    elif isinstance(s, str):
        s = shlex.split(s)
    else:
        raise TypeError("s should be None, str or list")
    for arg in s:
        key = None
        value = "True"
        # split arg on (keys string, value)
        splitted_arg = re.search("--([^=\n]+)(?:=(.*))?", arg)
        # if split successful, then set first captured group as key and
        # if second group is not None, set it as value ("True" string otherwise)
        if splitted_arg is not None:
            key = splitted_arg.groups()[0]
            if splitted_arg.groups()[1] is not None:
                value = splitted_arg.groups()[1]
        # if split fails, assume that we have positional argument and set value
        # to arg, when keeping key as None.
        else:
            value = arg
        # First, try to convert value to bool, after that to int, and then
        # keep as str
        try:
            value = int(value)
        except:
            pass
        try:
            value = str_to_bool(value)
        except:
            pass
        if key is None:
            args[0].append(value)
        else:
            args[1][key] = value
    return args


## Execute scenario.
#
# @param func Function, which represent scenario.
# @param script_name Name of script, needed for building log file name.
# @param script_args Positional args to `func`.
# @param script_kwargs Named args to `func`.
def main(func, script_name, script_args=(), script_kwargs={}):

    ## Wrapper for scenario, which do the necessary preparations, like creating
    #  PID file, logs, etc.
    #
    # @brief This function shouldn't be called directly,
    #  only from lib::common::bootstrap::main()
    #
    # @param func Function, which represent scenario.
    # @param script_name Name of script, needed for building log file name.
    # @param op_uuid UUID of global operation.
    # @param script_args Positional args to `func`.
    # @param script_kwargs Named args to `func`.
    def scenario_executor(func, script_name, op_uuid, script_args=(),
                          script_kwargs={}):
        # setting up pid file
        pid = os.getpid()
        pid_filename = os.path.join(gv.PID_PATH,
                                    "AutomationLibrary_{}.pid".format(pid))
        pid_file = open(pid_filename, "w")
        pid_file.write(str(pid))
        pid_file.close()
        # setting up logger
        log_folder = 'script_logs'
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)
        global_logger.add_file_handler(os.path.join(
            gv.PID_PATH, log_folder, script_name + "_" + str(
                datetime.datetime.now().strftime("%y%m%d_%H%M%S"))
            + "_" + str(os.getpid()) + ".log"
        ))
        global_logger.add_stream_handler(sys.stdout)
        # execute function, measure time and exit
        res = func(*script_args, **script_kwargs)
        _time = global_logger.finish_operation(op_uuid)
        global_logger.info(
            message="Scenario execution finished",
            duration=int(_time.microseconds * 10**-3 + _time.seconds * 10**3),
            scenario_name=script_name,
            code=res
        )
        try:
            os.remove(pid_filename)
        except:
            global_logger.warning(message="Couldn't remove pid file",
                                  pid_filename=pid_filename)
        # set return code and exit
        os._exit(res)

    op_uuid = global_logger.start_operation()
    thread = threading.Thread(target=scenario_executor, args=(func,
                                                              script_name,
                                                              op_uuid,
                                                              script_args,
                                                              script_kwargs))
    thread.start()
    # wait for setting up configuration
    import time
    config_read_timeout = 30
    i = 0
    while "time-limit" not in gv.CONFIG and i < config_read_timeout:
        time.sleep(0.1)
        i += 1
    # handle situation when reading configure is failed
    if i >= config_read_timeout:
        err = AutomationLibraryError("TIMEOUT_ERROR")
        global_logger.error(
            str(err), state="error"
        )
        time = global_logger.finish_operation(op_uuid)
        global_logger.info(message="Scenario execution finished",
                           duration=int(
                               time.microseconds * 10**-3 + time.seconds * 10**3
                           ),
                           scenario_name=script_name,
                           code=err.num_code)
        os.remove(os.path.join(gv.PID_PATH,
                               "AutomationLibrary_{}.pid".format(os.getpid())))
        os._exit(err.num_code)
    # setting time-limit
    thread.join(gv.CONFIG["time-limit"])
    # if time-limit is expired, kill script
    if thread.is_alive():
        err = AutomationLibraryError("TIMEOUT_ERROR")
        global_logger.error(
            str(err), state="error"
        )
        time = global_logger.finish_operation(op_uuid)
        global_logger.info(message="Scenario execution finished",
                           duration=int(
                               time.microseconds * 10**-3 + time.seconds * 10**3
                           ),
                           scenario_name=script_name,
                           code=err.num_code)
        os.remove(os.path.join(gv.PID_PATH,
                               "AutomationLibrary_{}.pid".format(os.getpid())))
        os._exit(err.num_code)
