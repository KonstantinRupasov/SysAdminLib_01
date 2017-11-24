import re
import os
import sys
import shlex
import subprocess as sp


from lib.common import bootstrap
from lib.common import global_vars as gv
from lib.common.config import *
from lib.utils.cvt import str_to_bool
from lib.utils import *
from lib.common.errors import *
from lib.common.logger import *


class CompositeStep:
    def __init__(self, data):
        # check, if data is dictionary
        if not isinstance(data, dict):
            raise AutomationLibraryError(
                "ARGS_ERROR", "step data should be dictionary", type=type(data),
            )
        # store data
        self.data = data.copy()
        if "name" not in self.data:
            raise AutomationLibraryError(
                "ARGS_ERROR", "option not found in step data",
                key="name"
            )
        # detecting type
        if "command" not in self.data and "command-string" in self.data:
            self._type = "string"
        elif "command" not in self.data and "command-string" not in self.data:
            raise AutomationLibraryError(
                "ARGS_ERROR", "step data is invalid. 'command' or "
                "'command-string' key should be specified",
                step_name=self.data["name"]
            )
        else:
            if "scenario-data" not in self.data:
                raise AutomationLibraryError(
                    "ARGS_ERROR", "step data is invalid. If you specify "
                    "'command', then you should also specify 'scenario-data'",
                    step_name=self.data["name"]
                )
            self._type = "dict"
        # if rollback not in data, set it to True
        if "rollback" not in self.data:
            self.data["rollback"] = True

    def _build_cmd_args(self, rollback):
        cmd_args = [sys.executable, os.path.join(sys.path[0], "agent.py")]
        if self._type == "dict":
            cmd_args.append(self.data["command"])
            for key, value in self.data["scenario-data"].items():
                cmd_args.append("--{}={}".format(key, value))
        else:
            cmd_args += list(shlex.split(self.data["command-string"]))
        cmd_args.append(
            "--rollback=disable" if not rollback else "--rollback=only"
        )
        return cmd_args

    def build_cmd_args(self):
        return self._build_cmd_args(False)

    def build_rollback_args(self):
        return self._build_cmd_args(True)

    @property
    def type(self):
        return self._type

    def execute(self):
        process = sp.Popen(self.build_cmd_args(), shell=False)
        process.wait()
        return process.poll()

    def rollback(self):
        if self.data["rollback"]:
            process = sp.Popen(self.build_rollback_args(), shell=False)
            process.wait()
            return process.poll()
        else:
            global_logger.info(message="Rollback disabled for step",
                               step_name=self.data["name"])
            return 0


class CompositeScenario:
    def __init__(self, config_path, cmd_args):
        l = LogFunc(message="initializing CompositeScenario object")
        self.config = ScenarioConfiguration(read_yaml(config_path))
        # if configuration is not composite, raise an exception
        if not self.config.composite:
            raise AutomationLibraryError("ARGS_ERROR", "configuration doesn't"
                                         "contain 'scenario' block",
                                         config_path=config_path)
        self.config.add_cmd_args(cmd_args[1])
        self.validate_config()
        gv.TEST_MODE = self.config["test-mode"]
        global_logger.debug(
            "Scenario data: " + str(self.config)
        )
        # set global CONFIG variable
        gv.CONFIG = self.config
        # make CompositeStep objects from composite data
        self.steps = [CompositeStep(data) for data \
                      in self.config.composite_scenario_data]


    def validate_config(self):
        pass


    def execute(self):
        l = LogFunc(message="Executing composite scenario", print_begin=True)
        result = 1
        counter = 0
        error_occurred = False
        for step in self.steps:
            counter += 1
            global_logger.info(
                message="******Step {}: {}******".format(
                    counter, step.data["name"]
                )
            )
            result = step.execute()
            if result != 0:
                error_occurred = True
                break
        # now, we have number of lust step in counter
        rollback_result = 1
        if error_occurred:
            for i in range(counter, 0, -1):
                if (self.steps[i-1].rollback()):
                    return AutomationLibraryError("ROLLBACK_ERROR").num_code
        else:
            return result


## Wrapper for scenario execution.
# @return Last error code (0 if no errors occurred).
def composite_scenario():
    res = 1
    # execute scenario
    try:
        scenario = CompositeScenario(sys.argv[1], bootstrap.parse_cmd_args())
        res = scenario.execute()
    # handle errors (ie log them and set return code)
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
    # and if no errors occurred, set return code to 0
    return res


if __name__ == "__main__":
    bootstrap.main(composite_scenario,
                   os.path.basename(__file__)[0:-3])
