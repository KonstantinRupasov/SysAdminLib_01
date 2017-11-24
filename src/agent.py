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
from time import sleep
import queue

from lib.common import bootstrap
from lib.common.errors import *
from lib.common.config import *
from lib.utils import *


AGENT_TEST_MODE = False
## How to execute rollback:
#  enable - if main scenario fails. This is default behavior;
#  disable - never;
#  only - execute only rollback scenario. This option intended to be used in
#  composite scenarios (when executing rollbacks in reverse order of steps).
ROLLBACK = "enable"


DICTIONARY_PATH = os.path.join(sys.path[0], "..", "..", "configs",
                               "dictionary.yaml")
COMPOSITE_RUNNER_NAME = "composite_runner.py"


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


class DictionaryEntry:
    def __init__(self, script, config, first_version=None, last_version=None,
                 exclude_versions=[], script_prefix="",
                 config_prefix=""):
        self.script = os.path.join(script_prefix, StrPathExpanded(script))
        try_open_file(self.script)
        self.config = os.path.join(config_prefix, StrPathExpanded(config))
        try_open_file(self.config)
        self.first_version = PlatformVersion(first_version)
        self.last_version = PlatformVersion(last_version)
        self.exclude_versions = [PlatformVersion(entry) \
                                 for entry in exclude_versions]

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

    def __repr__(self):
        return self.__str__()


class CommandDictionary:
    def __init__(self, path=None):
        self.data = {}
        if path:
            self.add_data_from_file(path)

    def add_data_from_file(self, path, script_prefix=None, config_prefix=None):
        file_data = read_yaml(path)
        script_prefix = os.path.dirname(os.path.realpath(__file__)) \
                        if script_prefix is None else script_prefix
        config_prefix = os.path.dirname(path) \
                        if config_prefix is None else config_prefix
        for key, value in file_data.items():
            try:
                self.data[key] = DictionaryEntry.from_dict(value, script_prefix,
                                                           config_prefix)
            except:
                raise AutomationLibraryError(
                    "ARGS_ERROR", "cannot build dictionary entry from supplied "
                    "data", key=key, value=value
                )

    def add_temp_composite_data(self, config):
        script_prefix = os.path.dirname(os.path.realpath(__file__))
        self.data[str(uuid.uuid4())] = DictionaryEntry(
            COMPOSITE_RUNNER_NAME, config, script_prefix=script_prefix
        )

    def __getitem__(self, key):
        return self.data[key]


def step_from_scenario_entry(entry, dictionary):
    if "command" in entry:
        command = entry["command"]
        rollback = entry["rollback"] if "rollback" in entry else False
        cmd_args = entry["scenario-data"] if "scenario-data" in entry else {}
        name = entry["name"] if "name" in entry else None
    else:
        args = bootstrap.parse_cmd_args(shlex.split(entry["command-string"]))
        command = args[0][0]
        rollback = entry["rollback"] if "rollback" in entry else False
        cmd_args = args[1]
        name = entry["name"] if "name" in entry else None
    # detect Step type
    config_path = dictionary[command].config
    config = ScenarioConfiguration(read_yaml(config_path))
    StepCls = CompositeStep if config.composite else SimpleStep
    # building step
    return StepCls(command, dictionary, cmd_args, rollback, name)



class FakeStep:
    def __init__(self, *args, **kwargs):
        pass

    def start_execution(self):
        pass

    def start_rollback(self):
        pass

    def kill(self):
        pass

    @property
    def result(self):
        return 0

    @property
    def rollback_result(self):
        return 0


class SimpleStep:
    def __init__(self, command, dictionary, cmd_script_args, rollback,
                 name=None):
        # thread variables
        self.proc = None
        self.queue = queue.Queue()
        self.quit_event = threading.Event()
        self.result = None
        # step variables
        self.script_path = dictionary[command].script
        self.config_path = dictionary[command].config
        self.rollback = rollback
        self.name = name
        self.cmd_script_args = cmd_script_args
        self.dictionary = dictionary
        # load configuration
        self.config = ScenarioConfiguration(read_yaml(self.config_path))
        self.config.add_cmd_args(cmd_script_args)
        # trying to find time_limit
        # TODO: also try to find it in cmd args
        try:
            self.time_limit = int(self.config["time-limit"])
        except:
            self.time_limit = None
        if not isinstance(self.time_limit, int):
            global_logger.warning(
                message="time-limit not found. It is not critical"
                ", but agent will never kill scenario"
            )
        # build rollback data, if self.rollback is True
        # if self.rollback or config doesn't contain rollback at all,
        # set rollback_step to FakeStep
        if self.rollback:
            self.rollback_step = self.get_rollback_step()
        else:
            self.rollback_step = FakeStep()

    def get_rollback_step(self):
        if self.config.rollback_scenario is None:
            return FakeStep()
        if isinstance(self.config.rollback_scenario, str):
            entry = {}
            # rollback itself shouldn't have rollback. Though, it doesn't matter
            # but could save few IO ops and little time on unnecessary readings
            entry["command-string"] = self.config.rollback_scenario
        else:
            entry = self.config.rollback_scenario
        # force entry name to "(rollback) name" and rollback value to False,
        # ie we do not want to rollback step load it rollback step
        entry["name"] = "(rollback)"
        entry["rollback"] = False
        return step_from_scenario_entry(entry, self.dictionary)

    def start_execution(self):
        def thread_main(self):
            @handle_automation_library_errors
            def wrapee(self):
                args = [sys.executable, self.script_path, self.config_path] \
                       + ["--{}={}".format(key, value) for key, value \
                          in self.cmd_script_args.items()]
                self.proc = sp.Popen(args)
                time_exceeded = False
                # set end time
                end = datetime.now() + timedelta(seconds=self.time_limit)
                while self.proc.returncode is None:
                    sleep(1)
                    self.proc.poll()
                    # if time-limit set and current time above it or if
                    # quite event set, raise an exception
                    if (isinstance(self.time_limit, int) \
                       and datetime.now() >= end) or self.quit_event.is_set():
                        time_exceeded = True
                        break
                # clean all processes, which was started
                if detect_actual_os_type() == "Windows":
                    from lib.win_utils import kill_process_tree
                else:
                    from lib.linux_utils import kill_process_tree
                kill_process_tree(self.proc.pid)
                # if time exceeded, raise an exception
                if time_exceeded:
                    raise AutomationLibraryError("TIMEOUT_ERROR")
                else:
                # return return code if external command finished successful
                    return self.proc.returncode

            global_logger.info(message="******Starting simple step******")
            global_logger.info(message="Step info", name=self.name,
                               script=self.script_path, config=self.config_path,
                               cmd_args=self.cmd_script_args)
            # set result in object
            self.quit_event.clear()
            self.result = wrapee(self)

        # reset flags and result in, just in case it was somehow corrupted
        self.result = None
        self.quit_event.clear()
        self.thread = threading.Thread(target=thread_main, args=(self,))
        self.thread.start()

    ## TODO: add check, if rollback disabled
    def start_rollback(self):
        self.rollback_step.start_execution()

    def kill(self):
        self.quit_event.set()

    @property
    def rollback_result(self):
        return self.rollback_step.result


class CompositeStep:
    def __init__(self, command, dictionary, cmd_script_args, rollback,
                 name=None):
        # thread variables
        self.queue = queue.Queue()
        self.quit_event = threading.Event()
        self.result = None
        self.last_executed_step = -1
        self.rollback_result = 0
        # step variables
        self.script_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), COMPOSITE_RUNNER_NAME
        )
        self.config_path = dictionary[command].config
        self.rollback = rollback
        self.name = name if name else command
        self.dictionary = dictionary
        self.cmd_script_args = cmd_script_args
        # load configuration
        self.config = ScenarioConfiguration(read_yaml(self.config_path))
        self.config.add_cmd_args(cmd_script_args)
        # set steps
        self.steps = []
        self.load_steps()
        # trying to find time_limit
        # TODO: also try to find it in cmd args
        try:
            self.time_limit = int(self.config["time-limit"])
        except:
            self.time_limit = None
        if not isinstance(self.time_limit, int):
            global_logger.warning(
                message="time-limit not found. It is not critical"
                ", but agent will never kill scenario"
            )
        # set rollback_step to self
        self.rollback_step = self

    def load_steps(self):
        for entry in self.config.composite_scenario_data:
            # AND entry rollback with scenario rollback to prevent circular
            # dependencies during loading rollbacks
            entry["rollback"] = self.rollback if "rollback" not in entry \
                                else (self.rollback and entry["rollback"])
            self.steps.append(step_from_scenario_entry(entry, self.dictionary))

    def start_execution(self):
        def thread_main(self):
            @handle_automation_library_errors
            def wrapee(self):
                time_exceeded = False
                last_result = 0
                step_in_progress = False
                # set end time
                end = datetime.now() + timedelta(seconds=self.time_limit)
                while True:
                    # if step not in progress, increase counter and start new
                    # step
                    if not step_in_progress:
                        step_in_progress = True
                        # if counter equal or more than length of steps,
                        # break loop, cuz we completed all steps
                        if (self.last_executed_step + 1) >= len(self.steps):
                            break
                        self.last_executed_step += 1
                        self.steps[self.last_executed_step].start_execution()
                        continue
                    # if step in progress, check, that time is not exceeded and
                    # quit event not set, after that check step state
                    else:
                        if (isinstance(self.time_limit, int) \
                            and datetime.now() >= end) \
                            or self.quit_event.is_set():
                            # if one of condition hit, break and raise exception
                            time_exceeded = True
                            break
                        step_result = self.steps[self.last_executed_step].result
                        if step_result is None:
                            sleep(1)
                            continue
                        # if step finished successful, start new step
                        if isinstance(step_result, int):
                            # kill step, just for sure
                            self.steps[self.last_executed_step].kill()
                            if step_result == 0:
                                step_in_progress = False
                                continue
                            else:
                                last_result = step_result
                                break
                # kill last step
                self.steps[self.last_executed_step].kill()
                # decide, what to do next
                if time_exceeded:
                    raise AutomationLibraryError("TIMEOUT_ERROR")
                else:
                    return last_result
            global_logger.info(message="******Starting composite step******")
            global_logger.info(message="Step info", name=self.name,
                               script=self.script_path, config=self.config_path,
                               cmd_args=self.cmd_script_args
            )
            # set result in object
            self.quit_event.clear()
            self.result = wrapee(self)

        # reset flags and result in, just in case it was somehow corrupted
        self.result = None
        self.last_executed_step = -1
        self.quit_event.clear()
        self.thread = threading.Thread(target=thread_main, args=(self,))
        self.thread.start()

    ## TODO: add check, if rollback disabled
    def start_rollback(self):
        def thread_main(self):
            @handle_automation_library_errors
            def wrapee(self):
                time_exceeded = False
                last_result = 0
                step_in_progress = False
                # set end time
                end = datetime.now() + timedelta(seconds=self.time_limit)
                while True:
                    # if step not in progress, increase counter and start new
                    # step
                    if not step_in_progress:
                        step_in_progress = True
                        self.steps[self.last_executed_step].start_rollback()
                        continue
                    # if step in progress, check, that time is not exceeded and
                    # quit event not set, after that check step state
                    else:
                        if (isinstance(self.time_limit, int) \
                            and datetime.now() >= end) \
                            or self.quit_event.is_set():
                            # if one of condition hit, break and raise exception
                            time_exceeded = True
                            break
                        step_result = self.steps[self.last_executed_step] \
                                          .rollback_result
                        if step_result is None:
                            sleep(1)
                            continue
                        # if step finished successful, start new step
                        if isinstance(step_result, int):
                            # kill step, just for sure
                            self.steps[self.last_executed_step].rollback_step \
                                                               .kill()
                            if step_result == 0:
                                step_in_progress = False
                                # if counter equal or less than zero,
                                # break loop, cuz we completed all rollback steps
                                if (self.last_executed_step - 1) <= -1:
                                    last_result = step_result
                                    break
                                else:
                                    self.last_executed_step -= 1
                                    continue
                            else:
                                last_result = step_result
                                break
                # kill last step
                self.steps[self.last_executed_step].kill()
                # decide, what to do next
                if time_exceeded:
                    raise AutomationLibraryError("TIMEOUT_ERROR")
                else:
                    return last_result

            global_logger.info(
                message="******Starting composite rollback step******"
            )
            global_logger.info(message="Step info", name=self.name,
                               script=self.script_path, config=self.config_path)
            # set result in object
            self.quit_event.clear()
            self.rollback_result = wrapee(self)

        # reset flags and result in, just in case it was somehow corrupted
        self.quit_event.clear()
        self.thread = threading.Thread(target=thread_main, args=(self,))
        self.thread.start()

    def kill(self):
        self.quit_event.set()



def agent_main():
    global_logger.info(message="******Starting agent******")
    dictionary = CommandDictionary(DICTIONARY_PATH)
    cmd_args = bootstrap.parse_cmd_args(sys.argv[1:])
    bootstrap.set_debug_values(cmd_args[1])
    main_config = ScenarioConfiguration(
        read_yaml(dictionary[cmd_args[0][0]].config)
    )
    main_config.add_cmd_args(cmd_args[1])
    #
    if main_config.composite:
        main_step = CompositeStep(cmd_args[0][0], dictionary, cmd_args[1], True)
    else:
        main_step = SimpleStep(cmd_args[0][0], dictionary, cmd_args[1], True)
    main_step.start_execution()
    main_step.thread.join()
    if main_step.result != 0:
        main_step.start_rollback()
        while main_step.rollback_result is None:
            sleep(1)
        return main_step.rollback_result
    else:
        return main_step.result


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
        gv.PID_PATH, log_folder, "agent" + "_" + str(
            datetime.now().strftime("%y%m%d_%H%M%S"))
        + "_" + str(os.getpid()) + ".log"
    ))
    global_logger.add_stream_handler(sys.stdout)
    # execute agent main function
    result = agent_main()
    # remove pid file
    try:
        os.remove(pid_filename)
    except:
        global_logger.warning(message="Couldn't remove pid file",
                              pid_filename=pid_filename)
    # return result
    sys.exit(result)


if __name__ == "__main__":
    main()
