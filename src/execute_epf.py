#!/usr/bin/python3
# coding: utf-8
import sys
import os
import subprocess as sp


from lib.common import bootstrap
from lib.common.config import *
from lib.utils import *
from lib.utils.cmd import *


class ExecuteEpfScenario:
    ## Constructor.
    # @param self Pointer to object.
    # @param config lib::common::config::Configuration object.
    # @param kwargs additional named args for config object.
    def __init__(self, config, **kwargs):
        l = LogFunc(message="initializing ExecuteEpfScenario object")
        self.config = config
        # set global test mode variable
        gv.TEST_MODE = self.config["test-mode"]
        # building path to 1cv8c executable
        client_exe = os.path.join(config["client-path"], "1cv8c")
        if config["os-type"] == "Windows":
            client_exe += ".exe"
        self.config["client-executable"] = client_exe
        # validate configuration
        self.validate_config()
        # set global CONFIG variable
        gv.CONFIG = self.config
        # log self.configuration
        global_logger.debug("Scenario data: " + str(self.config))

    ## Validating config.
    # @param self Pointer to object.
    # @exception AutomationLibraryError("OPTION_NOT_FOUND")
    # @exception AutomationLibraryError("OLD_VERSION_NOT_DETECTED")
    # @exception AutomationLibraryError("OLD_VERSION_DOESNT_MATCH")
    # @exception AutomationLibraryError("OPTION_NOT_FOUND")
    def validate_config(self):
        validate_data = [
            ["test-mode", bool],
            ["try-count", int],
            ["timeout", int],
            ["time-limit", int],
            ["os-type", str, str, ["Windows", "Linux-deb", "Linux-rpm"]],
            ["lang", str, str, gv.LANGS],
            ["epf-path", StrPathExpanded],
            ["client-path", StrPathExpanded],
            ["srvr", str],
            ["ib", str],
            ["command", str],
        ]
        self.config.validate(validate_data)
        # check, is .epf exists and we allowed to read it
        try_open_file(self.config["epf-path"])
        # check, is 1cv8c exists
        try_open_file(self.config["client-executable"])

    ## Execute scenario.
    # @param self Pointer to object.
    # @return Last return code
    def execute(self):
        l = LogFunc(message="executing epf", epf_path=self.config["epf-path"])
        # if test-mode is True, return immediately
        if self.config["test-mode"] is True:
            global_logger.info("Test mode completed successfully")
            return 0
        # building command line string
        cmd = [
            self.config["client-executable"], "/S",
            self.config["srvr"] + "\\" + self.config["ib"],
            "/Execute", self.config["epf-path"],
            "/C", self.config["command"], "/L" + self.config["lang"],
            "/DisableStartupDialogs"
        ]
        # if user and password set in config, add them to string
        if "usr" in self.config and "pwd" in self.config and \
           self.config["usr"] != "":
            cmd += ["/N", str(self.config["usr"]), "/P",
                    str(self.config["pwd"])]
        # execute epf
        try:
            res = run_cmd(cmd, timeout=self.config["timeout"])
        except sp.TimeoutExpired:
            raise AutomationLibraryError("TIMEOUT_ERROR")
        else:
            if res.returncode != 0:
                raise AutomationLibraryError("CMD_RESULT_ERROR",
                                             returncode=res.returncode)
        return 0


## Wrapper for scenario execution.
# @return Last error code (0 if no errors occurred).
def execute_epf_scenario():
    res = 1
    # execute scenario
    try:
        data = read_yaml(sys.argv[1])
        config = ScenarioConfiguration(data)
        cmd_args = bootstrap.parse_cmd_args(sys.argv[2:])
        config.add_cmd_args(cmd_args[1], True)
        bootstrap.set_debug_values(cmd_args[1])
        scenario = ExecuteEpfScenario(config)
        # execute scenario "try-count" times and store return code
        for attempt in range(config["try-count"] - 1, -1, -1):
            try:
                res = scenario.execute()
            except Exception as err:
                if attempt > 0:
                    global_logger.info("retrying",reason=err,
                                       attempts_left=attempt)
                else:
                    raise
            else:
                if res == 0:
                    break
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
    # print come information about errors
    if res == 4:
        global_logger.warning(
            message="EPF execution failed. Exact reason unknown." \
            "TIMEOUT_ERROR could mean that execution exceeded time as well as" \
            " that execution wasn't started due to login error, wrong rights" \
            " on IB or anything else. To see in specific what happened, run " \
            "script again and watch for the process."
        )
    if res < 0:
        global_logger.warning(
            message="1cv8c program was stopped by signal with code " + \
            str(res) + ". Absolute value of this code correspond to POSIX" \
            " signal."
        )
    if res == 0:
        global_logger.warning(
            message="Return code 0 mean only that 1cv8c returned 0. It " \
            "doesn't mean that EPF itself finished successful."
        )
    return res


if __name__ == "__main__":
    bootstrap.main(execute_epf_scenario,
                   os.path.basename(__file__)[0:-3])
