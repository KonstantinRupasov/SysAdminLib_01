#!/usr/bin/python3
# coding: utf-8
import sys
import os
import subprocess as sp
import datetime


from lib.common import bootstrap
from lib.common.config import *
from lib.utils import *
from lib.utils.cmd import *


class Update1CConfScenario:
    ## Constructor.
    # @param self Pointer to object.
    # @param config lib::common::config::Configuration object or path
    #  to YAML configuration file.
    # @param kwargs additional named args for config object.
    def __init__(self, config, **kwargs):
        l = LogFunc(message="initializing Update1CConfScenario object")
        self.config = config
        # set global test mode variable
        gv.TEST_MODE = self.config["test-mode"]
        # building path to 1cv8c executable
        client_exe = os.path.join(config["client-path"], "1cv8")
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
            # ["try-count", int],
            # ["timeout", int],
            ["time-limit", int],
            ["os-type", str, str, ["Windows", "Linux-deb", "Linux-rpm"]],
            ["srvr", str],
            ["ib", str],
            ["cf-name", str],
            # ["backup-folder", StrPathExpanded],
            ["distr-folder", StrPathExpanded],
            ["lang", str, str, gv.LANGS],
        ]
        self.config.validate(validate_data)

    def prepare(self):
        l = LogFunc(message="preparing to update 1C configuration")
        # detecting update type. It could be "cf" (ie "replace" configuration)
        # and "cfu" (ie update configuration with kind of "diff" file)
        cf_path = os.path.join(self.config["distr-folder"],
                                    self.config["cf-name"])
        update_type = None
        ext = os.path.splitext(cf_path)[1]
        if ext == ".cf":
            update_type = "cf"
        elif ext == ".cfu":
            update_type = "cfu"
        else:
            raise AutomationLibraryError(
                "ARGS_ERROR", "Unknown configuration file extension",
                file=cf_path
            )
        self.config["update-type"] = update_type

    def execute(self):
        # make preparations
        self.prepare()
        # begin update
        l = LogFunc(message="updating 1C configuration",
                    cf=os.path.join(self.config["distr-folder"],
                                    self.config["cf-name"]))
        # if test-mode is True, return immediately
        if self.config["test-mode"] is True:
            global_logger.info("Test mode completed successfully")
            return 0
        ### Stage 1. Update configuration. ###
        cf_path = os.path.join(self.config["distr-folder"],
                                    self.config["cf-name"])
        # building command line string
        cmd = [
            self.config["client-executable"], "DESIGNER",
            "/S", self.config["srvr"] + "\\" + self.config["ib"],
            "/LoadCfg" if self.config["update-type"] == "cf" else "/UpdateCfg",
            cf_path, "/DisableStartupDialogs",
            "/L" + self.config["lang"]
        ]
        # if user and password set in config, add them to string
        if "usr" in self.config and "pwd" in self.config and \
           self.config["usr"] != "":
            cmd += ["/N", str(self.config["usr"]), "/P",
                    str(self.config["pwd"])]
        # execute cmd
        try:
            res = run_cmd(cmd)
        except sp.TimeoutExpired:
            raise AutomationLibraryError("TIMEOUT_ERROR")
        else:
            if res.returncode != 0:
                raise AutomationLibraryError("CMD_RESULT_ERROR",
                                             returncode=res.returncode)
        ### Stage 2. Update database configuration. ###
        # building command line string
        cmd = [
            self.config["client-executable"], "DESIGNER",
            "/S", self.config["srvr"] + "\\" + self.config["ib"],
            "/UpdateDBCfg", "/L" + self.config["lang"], "/DisableStartupDialogs"
        ]
        # if user and password set in config, add them to string
        if "usr" in self.config and "pwd" in self.config and \
           self.config["usr"] != "":
            cmd += ["/N", str(self.config["usr"]), "/P",
                    str(self.config["pwd"])]
        # execute cmd
        try:
            res = run_cmd(cmd)
        except sp.TimeoutExpired:
            raise AutomationLibraryError("TIMEOUT_ERROR")
        else:
            if res.returncode != 0:
                raise AutomationLibraryError("CMD_RESULT_ERROR",
                                             returncode=res.returncode)


## Wrapper for scenario execution.
# @return Last error code (0 if no errors occurred).
def update_1c_conf_scenario():
    res = 1
    # execute scenario
    try:
        data = read_yaml(sys.argv[1])
        config = ScenarioConfiguration(data)
        cmd_args = bootstrap.parse_cmd_args(sys.argv[2:])
        config.add_cmd_args(cmd_args[1], True)
        bootstrap.set_debug_values(cmd_args[1])
        if "composite-scenario-name" in config:
            global_logger.info(
                message="Execute as part of composite scenario",
                composite_scenario_name=config["composite-scenario-name"]
            )
            config["standalone"] = False
        else:
            global_logger.info(
                message="Execute as standalone scenario"
            )
            config["standalone"] = True
        scenario = Update1CConfScenario(config)
        scenario.execute()
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
    else:
        res = 0
    # print come information about errors
    if res == 4:
        global_logger.warning(
            message="Updating 1C configuration execution failed."
            " Exact reason unknown." \
            "TIMEOUT_ERROR could mean that execution exceeded time as well as" \
            " that execution wasn't started due to login error, wrong rights" \
            " on IB or anything else. To see in specific what happened, run " \
            "script again and watch for the process."
        )
    if res < 0:
        global_logger.warning(
            message="1cv8 program was stopped by signal with code " + \
            str(res) + ". Absolute value of this code correspond to POSIX" \
            " signal."
        )
    if res == 0:
        global_logger.warning(
            message="Return code 0 mean only that 1cv8 returned 0. It " \
            "doesn't mean that update itself finished successful."
        )
    return res


if __name__ == "__main__":
    bootstrap.main(update_1c_conf_scenario,
                   os.path.basename(__file__)[0:-3])
