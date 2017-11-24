#!/usr/bin/python3
# coding: utf-8
import sys


from lib.common import bootstrap
from lib.common.config import *
from lib.platform_ctl import PlatformCtlScenario
from lib.utils import *


## Wrapper for scenario execution.
# @return Last error code (0 if no errors occurred).
def platform_start_scenario():
    res = -1
    # execute scenario
    try:
        data = read_yaml(sys.argv[1])
        config = ScenarioConfiguration(data)
        cmd_args = bootstrap.parse_cmd_args(sys.argv[2:])
        config.add_cmd_args(cmd_args[1], True)
        bootstrap.set_debug_values(cmd_args[1])
        scenario = PlatformCtlScenario(config, "start")
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
    # and if no errors occurred, set return code to 0
    else:
        res = 0
    return res


if __name__ == "__main__":
    bootstrap.main(platform_start_scenario,
                   os.path.basename(__file__)[0:-3])
