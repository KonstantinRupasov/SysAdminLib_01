#!/usr/bin/python3

import sys
import os
import yaml
import re
import subprocess as sp
import shlex
import uuid
import threading
from datetime import datetime, timedelta
import time
import queue


from lib.common import bootstrap
from lib.common.errors import *
from lib.common.config import *
from lib.utils import *


SLEEP_DELAY = 0.005
DICTIONARY_PATH = os.path.join(sys.path[0], "..", "..", "configs",
                               "dictionary.yaml")
COMPOSITE_RUNNER_NAME = "composite_runner.py"
TOP_LEVEL_SCENARIO_NAME = None
DICTIONARY = None


## Decorator, which capture AutomationLibraryErrors, log them and return
#  appropriate value.
def handle_automation_library_errors(func):
    def wrapper(*args, **kwargs):
        res = 1
        try:
            res = func(*args, **kwargs)
        except AutomationLibraryError as err:
            global_logger.error(
                str(err), state="error",
            )
            res = err.num_code
        except Exception as err:
            err = AutomationLibraryError("UNKNOWN", err)
            global_logger.error(
                str(err), state="error",
            )
            res = err.num_code
        return res
    return wrapper


## Add debug values from global_vars to destination dictionary copy.
# @param dst Destination dictionary.
# @return Copy of `dst` with debug values.
def add_debug_values(dst):
    dst = dst.copy()
    for key in ["debug", "collapse-traceback", "print-begin",
                "print-uuid", "print-function", "escape-strings"]:
        dst[key] = getattr(gv, key.upper().replace("-", "_"))
    return dst


## Try to build stage from data.
# @param data Data, which is used for building stage.
# @param classes List of classes, which will be used to create stage.
#  If first class fails on building stage, second will be used etc.
# @param dictionary CommandDictionary object.
# @return Stage object.
def build_stage(data, classes, dictionary):
    for Cls in classes:
        try:
            return Cls.from_data(data, dictionary)
        except Exception as err:
            global_logger.debug(
                message="Error occurred while building stage",
                cls=Cls.__name__,
                error=str(err)
            )
    raise AutomationLibraryError(
        "CONFIG_ERROR", "Unknown entry type", data=data,
        allowed_types=[i.__name__ for i in classes]
    )


## Cross-platform version of killing processes tree. This function encapsulate
#  detection of OS and setting proper kill_process_tree function.
# @param pid PID of root process.
@static_var("kill_func")
def kill_process_tree(pid):
    if kill_process_tree.__static_vars__.kill_func is None:
        if detect_actual_os_type() == "Windows":
            from lib.win_utils import kill_process_tree as f
        else:
            from lib.linux_utils import kill_process_tree as f
        kill_process_tree.__static_vars__.kill_func = f
    return kill_process_tree.__static_vars__.kill_func(pid)


## Class, which represent command dictionary entry.
class DictionaryEntry:
    ## Constructor.
    # @param self Pointer to object.
    # @param script Script name.
    # @param config Configuration file name.
    # @param first_version First version.
    # @param last_version Last version.
    # @param exclude_versions
    # @param script_prefix Prefix to script name (can be path).
    # @param config_prefix Prefix to configuration file name.
    # @param test_files Check, is files, specified in config-name and
    #  script-name, exists.
    def __init__(self, script, config, first_version=None, last_version=None,
                 exclude_versions=[], script_prefix="",
                 config_prefix="", test_files=False):
        self.script = os.path.join(script_prefix, StrPathExpanded(script))
        self.config = os.path.join(config_prefix, StrPathExpanded(config))
        if test_files:
            self.check_files()
        self.first_version = PlatformVersion(first_version)
        self.last_version = PlatformVersion(last_version)
        self.exclude_versions = [PlatformVersion(entry) \
                                 for entry in exclude_versions]

    ## Create DictionaryEntry object from dict.
    # @param data Dictionary with data.
    # @param script_prefix Prefix to script name (can be path).
    # @param config_prefix Prefix to configuration file name.
    @staticmethod
    def from_dict(data, script_prefix="", config_prefix=""):
        if "first-version" not in data:
            data["first-version"] = None
        if "last-version" not in data:
            data["last-version"] = None
        if "exclude-versions" not in data:
            data["exclude-versions"] = []
        return DictionaryEntry(
            data["script-name"], data["config-name"], data["first-version"],
            data["last-version"], data["exclude-versions"],
            script_prefix, config_prefix
        )

    ## String representation of object.
    # @param self Pointer to object.
    def __str__(self):
        s = "Script: {}, Config: {}".format(self.script, self.config)
        if self.first_version != None:
            s += ", First version: {}".format(self.first_version)
        if self.last_version != None:
            s += ", Last version: {}".format(self.last_version)
        if self.exclude_versions != []:
            s += ", Exclude versions: {}".format(
                ", ".join([str(i) for i in self.exclude_versions])
            )
        return s

    ## String representation of object.
    # @param self Pointer to object.
    def __repr__(self):
        return self.__str__()

    ## Check files existence and configuration correctness of configuration.
    # @param self Pointer to object.
    def check_files(self):
        try_open_file(self.script)
        try_open_file(self.config)
        ScenarioConfiguration(read_yaml(self.config))


## Class, which represent command dictionary.
class CommandDictionary:
    ## Constructor.
    # @param self Pointer to object.
    # @param path If specified, object will be initialized with data from file.
    def __init__(self, path=None):
        self.data = {}
        if path:
            self.add_data_from_file(path)

    ## Add data from file.
    # @param self Pointer to object.
    # @param path Path, where dictionary stored.
    # @param script_prefix Prefix, which will be added to all script fields.
    #  If not specified, will be set to path to composite_runner.py.
    # @param config_prefix Prefix, which will be added to all config fileds.
    #  If not specified, will be set to path to `path`.
    def add_data_from_file(self, path, script_prefix=None, config_prefix=None):
        # read dictionary file
        file_data = read_yaml(path)
        # set prefixes
        script_prefix = os.path.dirname(os.path.realpath(__file__)) \
                        if script_prefix is None else script_prefix
        config_prefix = os.path.dirname(path) \
                        if config_prefix is None else config_prefix
        # iterate over data and build DictionaryEntry objects.
        for key, value in file_data.items():
            try:
                self.data[key] = DictionaryEntry.from_dict(value, script_prefix,
                                                           config_prefix)
            # if cannot build entry, raise and error
            except:
                raise AutomationLibraryError(
                    "ARGS_ERROR", "cannot build dictionary entry from supplied "
                    "data", key=key, value=value
                )

    ## DEPRECATED
    def add_temp_composite_data(self, config):
        script_prefix = os.path.dirname(os.path.realpath(__file__))
        self.data[str(uuid.uuid4())] = DictionaryEntry(
            COMPOSITE_RUNNER_NAME, config, script_prefix=script_prefix
        )

    ## Provide access to entries via key.
    # @param self Pointer to object.
    # @param key Name of the entry.
    def __getitem__(self, key):
        return self.data[key]

    def __contains__(self, key):
        return key in self.data


## Class, which encapsulate step execution.
class StepExecutor:
    ## Constructor.
    # @param self Pointer to object.
    # @param step *Step object.
    # @param func_name String with name of function, which will be invoked.
    # @param args Positional arguments to function.
    # @param kwargs Named arguments for functions.
    # @param pass_quit_event If True, threading.Event() object will be passed
    #  as last positional argument. This event object initial set to False.
    #  If it switched to True, then function should terminate. Note that
    #  function can ignore this event, even if function accept it.
    def __init__(self, step, func_name, args=(), kwargs={},
                 pass_quit_event=True):
        self._quit_event = threading.Event()
        self._step = step
        self._target_func = getattr(self._step, func_name)
        if pass_quit_event:
            args += (self._quit_event, )
        self._result = None
        self._thread = threading.Thread(target=self._thread_main, args=args,
                                        kwargs=kwargs)
        self._thread.start()

    ## Function, which will be actually main in thread.
    def _thread_main(self, *args, **kwargs):
        self._quit_event.clear()
        # self._step passed automatically
        self._result = self._target_func(*args, **kwargs)
        if hasattr(self._step, "name"):
            global_logger.info(message="Step result", step=self._step.name,
                               result=self.result)
        else:
            global_logger.info(message="Step result", result=self.result)

    ## Join to inner thread object.
    # @param self Pointer to object.
    # @param timeout Timeout. Works the same as in threading.Thread.join().
    def join(self, timeout=None):
        self._thread.join(timeout)

    ## Ask to kill step. Note that if step's function doesn't accept quit_event
    #  or ignore it, this function will do nothing and return True. This
    #  can be called on already finished step, and will return True.
    # @param self Pointer to object.
    # @return True, if thread finished, False otherwise.
    def kill(self):
        self._quit_event.set()
        self._thread.join(SLEEP_DELAY*100)
        return not self.is_alive()
        # TODO: decide what to do if kill fails

    ## Get result value.
    # @param self Pointer to object.
    @property
    def result(self):
        return self._result

    ## Check, is executor finished.
    # @param self Pointer to object.
    def is_alive(self):
        if self._result is not None and self._thread.is_alive():
            global_logger.warning(
                message="StepExecutor: result is set, but thread still alive.",
                target_func=self._target_func.__name__
            )
        return self._thread.is_alive()


## Class, which define abstract stage. All stage classes should be inherited
#  from this class.
class AbstractStage:

    ## Constructor.
    # @param self Pointer to object.
    def __init__(self):
        self._time_limit = 0

    ## Build stage from data and dictionary.
    # @param cls Class.
    # @param data Data, which is define stage.
    # @param dictionary CommandDictionary object.
    @classmethod
    def from_data(cls, data, dictionary):
        pass

    ## Execute stage. Should return StepExecutor.
    # @param self Pointer to object.
    def execute(self):
        pass

    ## Rollback stage. Can be not implemented (should return None in this case).
    # @param self Pointer to object.
    def rollback(self):
        pass

    ## Get time-limit value.
    # @param self Pointer to object.
    # @return time-limit value.
    @property
    def time_limit(self):
        return self._time_limit

    ## Set time-limit value.
    # @param self Pointer to object.
    # @param time_limit New value.
    # @exception TypeError New value is not an integer.
    # @exception ValueError New value less than zero.
    @time_limit.setter
    def time_limit(self, time_limit):
        if not isinstance(time_limit, int):
            raise TypeError("time_limit should be 'int")
        if time_limit < 0:
            raise ValueError("time_limit should be zero or positive")
        self._time_limit = time_limit


## Class, which is responsible for running simple scenarios' scripts.
class PrimitiveStage(AbstractStage):

    ## Constructor.
    # @param self Pointer to object.
    def __init__(self):
        self.name = None
        self.scenario_data = None
        self.script_path = None
        self.config_path = None
        self._time_limit = 0
        self._try_count = 1
        self._timeout = 0

    ## Get timeout value.
    # @param self Pointer to object.
    # @return Timeout value.
    @property
    def timeout(self):
        return self._timeout

    ## Set timeout value.
    # @param self Pointer to object.
    # @param timeout New value.
    # @exception TypeError New value is not an integer.
    # @exception ValueError New value less than zero.
    @timeout.setter
    def timeout(self, timeout):
        if not isinstance(timeout, int):
            raise TypeError("timeout should be 'int")
        if timeout < 0:
            raise ValueError("timeout should be zero or positive")
        self._timeout = timeout

    ## Get try-count value.
    # @param self Pointer to object.
    # @return Try count value.
    @property
    def try_count(self):
        return self._try_count

    ## Set try-count value.
    # @param self Pointer to object.
    # @param try_count New value.
    # @exception TypeError New value is not an integer.
    # @exception ValueError New value not positive.
    @try_count.setter
    def try_count(self, try_count):
        if not isinstance(try_count, int):
            raise TypeError("try_count should be 'int")
        if try_count < 1:
            raise ValueError("try_count should be positive")
        self._try_count = try_count

    ## Try to detect in config and set time variables.
    # @param self Pointer to object.
    def set_time_variables(self):
        try:
            self.time_limit = self.config["time-limit"]
        except:
            pass
        try:
            self.timeout = self.config["timeout"]
        except:
            pass
        try:
            self.try_count = self.config["try-count"]
        except:
            pass

    ## Build stage from data and dictionary. New objects of this class should be
    #  created only via this method, not directly.
    # @param cls Class.
    # @param data Data, which is define stage.
    # @param dictionary CommandDictionary object.
    # @exception KeyError If returned, then no command in data, try different type.
    @classmethod
    def from_data(cls, data, dictionary):
        obj = PrimitiveStage()
        obj.script_path = dictionary[data["command"]].script
        obj.config_path = dictionary[data["command"]].config
        obj.config = ScenarioConfiguration(read_yaml(obj.config_path))
        # this allow absence of scenario-data key in config
        obj.cmd_args = data["scenario-data"] if "scenario-data" in data else {}
        # now we can check, if cmd_args enough for configuration
        # first, make sure that we paobjed neceobjary keys via cmd
        obj.config.add_cmd_args(obj.cmd_args, True)
        # and then check, that no Placeholders left
        if not obj.config.is_complete():
            raise AutomationLibraryError(
                "CONFIG_ERROR", "Placeholders left in configuration",
                config=obj.config_path, cmd_args=obj.cmd_args
            )
        # if name presented, set it, otherwise command used as name
        obj.name = data["name"] if "name" in data else data["command"]
        obj.set_time_variables()
        return obj

    ## Wrapper around main() method, which handle retrying main()
    #  on fail, if try-count more than one.
    # @param self Pointer to object.
    # @param cmd_args args, which will be passed to main().
    # @param _quit_event Quit event (details in StepExecutor documentation).
    def _retry_main(self, cmd_args, _quit_event):
        # if try_count is less or equal to one,
        if self.try_count <= 1:
            return self._main(cmd_args, _quit_event)
        global_logger.info(message="Step will be retried on fail",
                           name=self.name,
                           try_count=self.try_count,
                           timeout=self.timeout)
        res = 1
        for i in range(1, self.try_count+1):
            res = self._main(cmd_args, _quit_event)
            global_logger.info(message="Attempt result",
                               attempt=i, result=res)
            if res == 0:
                return res
            if self.timeout > 0:
                time.sleep(self.timeout)
        return res

    ## Main function (ie which should be executed to perform step).
    # @param self Pointer to object.
    # @param cmd_args args, which will be passed to main().
    # @param _quit_event Quit event (details in StepExecutor documentation).
    @handle_automation_library_errors
    def _main(self, cmd_args, _quit_event):
        global_logger.info(message="****** Starting primitive stage ******")
        global_logger.info(message="Info",
                           script=self.script_path, config=self.config_path,
                           cmd_args=cmd_args, name=self.name)
        # convert self.cmd_args to command-line format
        args = [sys.executable, self.script_path, self.config_path] \
               + ["--{}={}".format(key, value) for key, value \
                  in cmd_args.items()]
        proc = sp.Popen(args)
        time_exceeded = False
        interrupted = False
        # set end time
        end = datetime.now() + timedelta(seconds=self.time_limit)
        while proc.returncode is None:
            time.sleep(SLEEP_DELAY)
            proc.poll()
            # if time-limit set and current time above it or if
            # quite event set, raise an exception
            if (isinstance(self.time_limit, int) \
                and datetime.now() >= end):
                kill_process_tree(proc.pid)
                raise AutomationLibraryError("TIMEOUT_ERROR")
            if _quit_event.is_set():
                kill_process_tree(proc.pid)
                raise AutomationLibraryError("INTERRUPTED")
        # clean all processes, which was started
        kill_process_tree(proc.pid)
        return proc.returncode

    ## Execute stage.
    # @param self Pointer to object.
    # @param test_mode Indicates whether stage should be executed in test mode
    #  or not.
    # @param standalone Indicates whether stage should be executed as standalone
    #  scenario or not.
    # @return StepExecutor object, which executes _main() method.
    def execute(self, test_mode, standalone):
        # make copy of self.cmd_args
        cmd_args = self.cmd_args.copy()
        # add additional fields
        cmd_args = add_debug_values(self.cmd_args)
        cmd_args["test-mode"] = test_mode
        cmd_args["standalone"] = standalone
        if not standalone:
            cmd_args["composite-scenario-name"] = TOP_LEVEL_SCENARIO_NAME
        return StepExecutor(self, "_retry_main", (cmd_args, ))


class StepStage(AbstractStage):

    ## Constructor.
    # @param self Pointer to object.
    def __init__(self):
        self.forward_step = None
        self.rollback_step = None
        self._interruptable = False

    ## Build stage from data and dictionary. New objects of this class should be
    #  created only via this method, not directly.
    # @param cls Class.
    # @param data Data, which is define stage.
    # @param dictionary CommandDictionary object.
    # @exception KeyError If returned, then no command in data, try different type.
    @classmethod
    def from_data(cls, data, dictionary):
        obj = StepStage()
        data = data.copy()
        # first: analyze data and split it
        if "rollback" not in data:
            rollback_data = None
        else:
            rollback_data = data["rollback"]
            # clear data from rollback before passing it to stage constructor
            del data["rollback"]
        # forward step
        obj.forward_step = PrimitiveStage.from_data(data, dictionary)
        # rollback step, if data provided
        if rollback_data is not None:
            rollback_data["name"] = "(rollback) " + obj.forward_step.name
            obj.rollback_step = PrimitiveStage.from_data(rollback_data,
                                                         dictionary)
        else:
            obj.rollback_step = None
        return obj

    ## Execute stage.
    # @param self Pointer to object.
    # @param test_mode Indicates whether stage should be executed in test mode
    #  or not.
    # @return StepExecutor object, which executes _main() method.
    def execute(self, test_mode):
        return self.forward_step.execute(test_mode, False)

    ## Execute rollback.
    # @param self Pointer to object.
    # @return StepExecutor object, which executes _main() method, if rollback
    #  enabled, None otherwise.
    def rollback(self):
        return self.rollback_step.execute(False, False) \
            if self.rollback_step is not None else None


class SequenceStage(AbstractStage):

    ## Constructor.
    # @param self Pointer to object.
    def __init__(self):
        self.steps = []
        self.interruptable_flags = []
        self.progress = -1
        self._gentle_quit_event = threading.Event()

    ## Build stage from data and dictionary. New objects of this class should be
    #  created only via this method, not directly.
    # @param cls Class.
    # @param data Data, which is define stage.
    # @param dictionary CommandDictionary object.
    # @exception KeyError If returned, then no command in data, try different type.
    @classmethod
    def from_data(cls, data, dictionary):
        obj = SequenceStage()
        data = data.copy()
        # check that data is actually sequence stage
        if not isinstance(data, list):
            raise AutomationLibraryError(
                "CONFIG_ERROR", "Sequence stage should be a list"
            )
        for entry in data:
            obj.interruptable_flags.append(
                "interruptable" in entry and entry["interruptable"]
            )
            obj.steps.append(build_stage(entry,
                                         [StepStage, SequenceStage,
                                          ParallelStage],
                                         dictionary))
        return obj

    ## Main function (ie which should be executed to perform step).
    # @param self Pointer to object.
    # @param test_mode Step should run only test mode.
    # @param debug Enable debug variables.
    # @param rollback Should function perform rollback or not.
    # @param _quit_event Quit event (details in StepExecutor documentation).
    # @return Result of last step (successful or not).
    @handle_automation_library_errors
    def _main(self, test_mode, rollback, _quit_event):
        global_logger.info(message="****** Starting sequence stage ******")
        last_result = 0
        current_executor = None
        if rollback:
            self.progress += 1
        while True:
            if current_executor is None:
                if self._gentle_quit_event.is_set():
                        raise AutomationLibraryError("INTERRUPTED")
                if not rollback:
                    if self.progress >= len(self.steps) - 1:
                        break
                    self.progress += 1
                    current_executor = self.steps[self.progress] \
                                           .execute(test_mode)
                else:
                    self.progress -= 1
                    if self.progress <= -1:
                        break
                    current_executor = self.steps[self.progress]\
                                           .rollback()
            else:
                if _quit_event.is_set():
                    current_executor.kill()
                    raise AutomationLibraryError("INTERRUPTED")
                # if asked gentle kill and not rollback and current step is
                # interrputable
                if self._gentle_quit_event.is_set() and not rollback \
                   and self.interruptable_flags[self.progress]:
                    current_executor.kill()
                    raise AutomationLibraryError("INTERRUPTED")
                if current_executor.is_alive():
                    time.sleep(SLEEP_DELAY)
                    continue
                # if result became an int value, utilize current executor
                # and start next step
                if isinstance(current_executor.result, int):
                    # kill step, just for sure
                    current_executor.kill()
                    last_result = current_executor.result
                    # if step finished successful, start new step
                    if last_result == 0:
                        current_executor = None
                    else:
                        break
        if current_executor:
            current_executor.kill()
        return last_result

    ## Execute stage.
    # @param self Pointer to object.
    # @param test_mode Indicates whether stage should be executed in test mode
    #  or not.
    # @return StepExecutor object, which executes _main() method.
    def execute(self, test_mode):
        self.progress = -1
        self._gentle_quit_event.clear()
        return StepExecutor(self, "_main", (test_mode, False))

    ## Execute rollback.
    # @param self Pointer to object.
    # @return StepExecutor object, which executes _main() method, if rollback
    #  enabled, None otherwise.
    def rollback(self):
        return StepExecutor(self, "_main", (False, True))

    ## Kill sequence gently (ie doesn't interrupt non-interruptable steps).
    #  This method have effect only on execute().
    # @param self Pointer to object.
    def gentle_kill(self):
        self._gentle_quit_event.set()


class ParallelStage(AbstractStage):

    ## Constructor.
    # @param self Pointer to object.
    def __init__(self):
        self.branches = []

    ## Build stage from data and dictionary. New objects of this class should be
    #  created only via this method, not directly.
    # @param cls Class.
    # @param data Data, which is define stage.
    # @param dictionary CommandDictionary object.
    # @exception KeyError If returned, then no command in data, try different type.
    @classmethod
    def from_data(cls, data, dictionary):
        obj = ParallelStage()
        try:
            # extract data
            data = data["parallel"].copy()
        except:
            raise AutomationLibraryError(
                "CONFIG_ERROR", "'parallel' keyword not found in entry",
                entry=data
            )
        for entry in data:
            # the only allowed type in each entry is sequence, even if it only
            # one element, so if entry is not list, convert it to list and pass
            # to SequenceStage constructor
            if not isinstance(entry, list):
                entry = [entry, ]
            obj.branches.append(build_stage(entry, [SequenceStage, ],
                                            dictionary))
        return obj

    ## Main function (ie which should be executed to perform step).
    # @param self Pointer to object.
    # @param test_mode Step should run only test mode.
    # @param rollback Should function perform rollback or not.
    # @param _quit_event Quit event (details in StepExecutor documentation).
    # @return Result of last step (successful or not).
    @handle_automation_library_errors
    def _main(self, test_mode, rollback, _quit_event):
        global_logger.info(message="****** Starting parallel stage ******")
        executors = []
        # this flag indicates that tasks should be interrupted, if possible
        interrupt = False
        first_failed_executor = None
        # start each step
        for branch in self.branches:
            if not rollback:
                executors.append(branch.execute(test_mode))
            else:
                # this needs for allow scenario dont have rollback
                executor = branch.rollback()
                if executor is not None:
                    executors.append(executor)
        # main loop, which will be executed until all executor finish or event is set
        while not _quit_event.is_set():
            time.sleep(SLEEP_DELAY)
            not_finished_found = False
            # check each executor
            for executor in executors:
                # if result of executor is 0, then it finished and no actions
                # required, just go check other
                if executor.result == 0:
                    continue
                # if result is None, then
                elif executor.result is None:
                    not_finished_found = True
                    if interrupt:
                        executor._step.gentle_kill()
                    continue
                # if result not None nor 0, execution finished with error
                elif isinstance(executor.result, int) and executor.result != 0:
                    if not interrupt:
                        interrupt = True
                        first_failed_executor = executor
            if not not_finished_found:
                break
        # if quit_event set, raise an exception
        if _quit_event.is_set():
            for executor, _ in executors:
                executor.kill()
            raise AutomationLibraryError("INTERRUPTED")
        # if found failed executor, return it result
        if first_failed_executor is not None:
            global_logger.info(
                message="One of the tasks of parallel stage failed",
                result=first_failed_executor.result
            )
            return first_failed_executor.result
        else:
            global_logger.info(
                message="All tasks of parallel stage completed successful",
                result=0
            )
            return 0

    ## Execute stage.
    # @param self Pointer to object.
    # @param test_mode Indicates whether stage should be executed in test mode
    #  or not.
    # @return StepExecutor object, which executes _main() method.
    def execute(self, test_mode):
        return StepExecutor(self, "_main", (test_mode, False))

    ## Execute rollback.
    # @param self Pointer to object.
    # @return StepExecutor object, which executes _main() method, if rollback
    #  enabled, None otherwise.
    def rollback(self):
        return StepExecutor(self, "_main", (False, True))


## Function, which is sort of "main" for composite scenarios execution.
# @param config ScenarioConfiguration object.
# @param disable_test_run Flag, which indicate that tests shouldn't be run.
# @param disable_rollback Flag, which indicate that rollback shouldn't be run.
# @return Integer representation of result.
def execute_composite_scenario(config, disable_test_run, disable_rollback):
    main_step = SequenceStage.from_data(config.composite_scenario_data,
                                        DICTIONARY)
    if not disable_test_run:
        global_logger.info(message="****** Starting test run ******")
        main_executor = main_step.execute(True)
        main_executor.join(config["time-limit"])
        main_executor.kill()
        global_logger.info(message="Test run result",
                           returncode=main_executor.result)
        if main_executor.result != 0:
            global_logger.info(message="****** Test run failed! ******",
                               returncode=main_executor.result)
            return main_executor.result
    else:
        global_logger.warning(message="Test run disabled")
    gv.TEST_MODE = False
    global_logger.info(message="****** Starting real run ******")
    main_executor = main_step.execute(False)
    main_executor.join(config["time-limit"])
    main_executor.kill()
    global_logger.info(message="Real run result",
                       returncode=main_executor.result)
    real_run_result = main_executor.result
    # if real run finished with error, store this result and run rollback
    if main_executor.result != 0:
        if not disable_rollback:
            global_logger.info(message="****** Starting rollback ******")
            main_executor = main_step.rollback()
            if main_executor is None:
                global_logger.info(message="No rollback specified")
                return real_run_result
            main_executor.join()
            main_executor.kill()
            global_logger.info(message="Rollback result",
                               returncode=main_executor.result)
        else:
            global_logger.warning(message="Rollback disabled")
            return real_run_result
    if main_executor.result == 0:
        return real_run_result
    else:
        raise AutomationLibraryError("ROLLBACK_ERROR")


## Function, which is sort of "main" for composite scenarios execution.
# @param command Command name.
# @param cmd_args Dictionary with command line named arguments.
# @param config ScenarioConfiguration object.
# @return Integer representation of result.
def execute_simple_scenario(command, cmd_args, config):
    forward_data = {
        "command": command,
        "scenario-data" : cmd_args
    }
    rollback_data = config.rollback_scenario
    forward_step = PrimitiveStage.from_data(forward_data, DICTIONARY)
    global_logger.info(message="****** Starting real run ******")
    main_executor = forward_step.execute(config["test-mode"], True)
    main_executor.join(forward_step.time_limit)
    main_executor.kill()
    global_logger.info(message="Real run result",
                       returncode=main_executor.result)
    real_run_result = main_executor.result
    if main_executor.result != 0:
        if rollback_data is None:
            global_logger.info(message="No rollback specified")
            return real_run_result
        rollback_step = PrimitiveStage.from_data(rollback_data, DICTIONARY)
        global_logger.info(message="****** Starting rollback ******")
        main_executor = rollback_step.execute(False, True)
        main_executor.join()
        main_executor.kill()
        global_logger.info(message="Rollback result",
                           returncode=main_executor.result)
    if main_executor.result == 0:
        return real_run_result
    else:
        raise AutomationLibraryError("ROLLBACK_ERROR")


## Function, which is responsible for reading command dictionary,
#  command line parsing and starting execution of necessary scenario type.
# @return Integer representation of result.
@handle_automation_library_errors
def composite_runner_main():
    global_logger.info(message="****** Starting composite runner ******")
    # parsing cmd args
    cmd_args = bootstrap.parse_cmd_args(sys.argv[1:])
    # setting debug values from cmd args
    bootstrap.set_debug_values(cmd_args[1])
    # replace dictionary path, if second positional argument provided
    if len(cmd_args[0]) > 1:
        global DICTIONARY_PATH
        DICTIONARY_PATH = StrPathExpanded(cmd_args[0][1])
        try:
            try_open_file(DICTIONARY_PATH)
        except:
            raise AutomationLibraryError(
                "ARGS_ERROR", "Cannot find or access dictionary file",
                path=StrPathExpanded(DICTIONARY_PATH)
            )
    # building dictionary
    global DICTIONARY
    DICTIONARY = CommandDictionary(DICTIONARY_PATH)
    # reading main config
    main_config = ScenarioConfiguration(
        read_yaml(DICTIONARY[cmd_args[0][0]].config)
    )
    main_config.add_cmd_args(cmd_args[1])
    if not main_config.is_complete():
        raise AutomationLibraryError(
            "CONFIG_ERROR", "Placeholders left in configuration",
            config=DICTIONARY[cmd_args[0][0]].config, cmd_args=cmd_args[1]
        )
    # set global top-level scenario name
    global TOP_LEVEL_SCENARIO_NAME
    TOP_LEVEL_SCENARIO_NAME = cmd_args[0][0]
    # building main step
    if main_config.composite:
        return execute_composite_scenario(
            main_config,
            "disable-test-run" in cmd_args[1] \
            and cmd_args[1]["disable-test-run"],
            "disable-rollback" in cmd_args[1] \
            and cmd_args[1]["disable-rollback"]
        )
    else:
        return execute_simple_scenario(
            cmd_args[0][0], cmd_args[1], main_config
        )


## Main function.
def main():
    # creating pid file
    pid = os.getpid()
    pid_filename = os.path.join(gv.PID_PATH,
                                "AutomationLibrary_{}.pid".format(pid))
    pid_file = open(pid_filename, "w")
    pid_file.write(str(pid))
    pid_file.close()
    # creating agent log
    log_folder = 'script_logs'
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)
    global_logger.add_file_handler(os.path.join(
        gv.PID_PATH, log_folder, "composite_runner" + "_" + str(
            datetime.now().strftime("%y%m%d_%H%M%S"))
        + "_" + str(os.getpid()) + ".log"
    ))
    global_logger.add_stream_handler(sys.stdout)
    # execute agent main function
    result = composite_runner_main()
    # remove pid file
    try:
        os.remove(pid_filename)
    except:
        global_logger.warning(message="Couldn't remove pid file",
                              pid_filename=pid_filename)
    # return result
    sys.exit(result)


if __name__=="__main__":
    main()
