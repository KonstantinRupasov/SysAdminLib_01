import yaml
import subprocess as sp
import sys
import os
import time
from functools import reduce


from lib.common import bootstrap
from lib.common.errors import *
from lib.common.logger import *
from lib.utils import *
from lib.utils.cmd import run_cmd
from lib.common import global_vars as gv


class GroupRunConfiguration:
    ## Constructor
    # @param self Pointer to object.
    # @param config_path Path to YAML configuration.
    def __init__(self, config_path, parsed_args=None):
        # set python executable path and agent.py path
        self.python = sys.executable
        self.agent_path = os.path.join(sys.path[0], "agent.py")
        # load and parse YAML config file
        data = read_yaml(config_path)
        # set variables
        self.version = data["version"]
        self.command = data["command-type"]
        self.test_mode = data["test-mode"]
        self.try_count = data["try-count"]
        self.timeout = data["timeout"]
        self.time_limit = data["time-limit"]
        # parse and set metadata
        self.defaults = data["scenario-meta-data"]["defaults"]
        # set data sets
        self.data_sets = data["scenario-data-sets"]
        # if parsed_args passed, extract necessary values from there, if they
        # supplied
        for arg in parsed_args:
            if arg[0][0] == "test-mode":
                self.test_mode = arg[1]
            if arg[0][0] == "timeout":
                self.timeout = arg[1]
            if arg[0][0] == "try-count":
                self.try_count = arg[1]
            if arg[0][0] == "time-limit":
                self.time_limit = arg[1]
        # set also global_vars
        gv.CONFIG["timeout"] = self.timeout
        gv.CONFIG["time-limit"] = self.time_limit
        gv.CONFIG["try-count"] = self.try_count
        gv.TEST_MODE = self.test_mode
        # set debug and time limit constants
        for data_set in self.data_sets:
            data_set["timeout"] = self.timeout
            data_set["time-limit"] = self.time_limit
            data_set["try-count"] = self.try_count
            data_set["print-begin"] = gv.PRINT_BEGIN
            data_set["print-uuid"] = gv.PRINT_UUID
            data_set["print-function"] = gv.PRINT_FUNCTION
            data_set["debug"] = gv.DEBUG
            data_set["collapse-traceback"] = gv.COLLAPSE_TRACEBACK
        # set defaults in data_sets
        for key, value in self.defaults.items():
            for data_set in self.data_sets:
                if key not in data_set:
                    data_set[key] = value
        global_logger.debug(message="Data sets",data_sets=self.data_sets)

    ## Get list of generated lists of args for agent.py
    # @param self Pointer to object.
    # @return List of lists with args (each list is same format as for
    #  subprocess.Popen)
    def get_agent_commands(self):
        result = list()
        for data_set in self.data_sets:
            result.append(
                [self.python, self.agent_path, self.command] + \
                ["--{}={}".format(key, value) for key, value in \
                 data_set.items()]
            )
        return result


## Constructor for "!join" tag in YAML. For parameters explanation see the
#  PyYAML documentation.
# @param loader
# @param node
# @return builded node.
def join(loader, node):
    seq = loader.construct_sequence(node)
    return ''.join([str(i) for i in seq])


## Constructor for "!getvalue" tag in YAML. For parameters explanation see the
#  PyYAML documentation.
# @param loader
# @param node
# @return builded node.
def getvalue(loader, node):
    seq = loader.construct_sequence(node)
    var = seq[0]
    for key in seq[1:]:
        var = var[key]
    return var


# add custom constructors to YAML loader
yaml.add_constructor('!join', join)
yaml.add_constructor('!getvalue', getvalue)


## Check, is subprocess.Popen process finished.
# @param process subprocess.Popen object.
# @return True if finished, False otherwise.
def check_process_finished(process):
            process.poll()
            return process.returncode is not None


## Run group task.
# @return Last result code.
def run_group():
    res = 1
    try:
        # create configuration object
        cfg = GroupRunConfiguration(sys.argv[1], bootstrap.parse_cmd_args())
        # processes pool
        proc_pool = list()
        # fill processes pool
        for cmd_args in cfg.get_agent_commands():
            proc_pool.append(sp.Popen(cmd_args, stdout=sp.PIPE, stderr=sp.PIPE))
        # wait until all processes finished
        step = 3
        counter = 0
        while (not reduce(lambda x, y: x and check_process_finished(y),
                         proc_pool, True)) and counter < cfg.timeout:
            time.sleep(step)
            counter += step
        # print result
        results = list()
        for proc in proc_pool:
            # try to communicate with process, and if fails, kill process
            # and all its children
            try:
                stdout, stderr = proc.communicate(timeout=1)
            except sp.TimeoutExpired:
                if detect_actual_os_type() == "Windows":
                    from lib.win_utils import kill_process_tree
                else:
                    from lib.linux_utils import kill_process_tree
                kill_process_tree(proc.pid)
                # stdout, stderr = proc.communicate()
            global_logger.info(message="task result", task_pid=proc.pid,
                               returncode=proc.returncode, args=proc.args)
            results.append(proc.returncode)
        # if counter exceeded timeout, raise an error
        if counter >= cfg.timeout:
            raise AutomationLibraryError("TIMEOUT_ERROR")
        # if result contain non-zero code, raise an error
        if set(results) != set([0]):
            raise AutomationLibraryError(
                "CMD_RESULT_ERROR",
                additional_message="one of the tasks returned non-zero code"
            )
    # handle errors
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
    else:
        res = 0
    return res


if __name__ == "__main__":
    bootstrap.main(run_group,
                   os.path.basename(__file__)[0:-3])
