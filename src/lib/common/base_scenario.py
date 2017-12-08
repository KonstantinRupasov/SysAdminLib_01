import sys
import os


from . import bootstrap
from .errors import *
from .logger import *
from ..utils import *
from ..utils.cmd import run_cmd
from . import global_vars as gv
from .config import *


class BaseScenario:
    # these methods should not be redefined in inherited classes without
    # strong reason

    ## Constructor.
    # @param self Pointer to object.
    # @param config lib::common::config::Configuration object.
    def __init__(self, config):
        l = LogFunc(message="initializing {} object".format(
            self.__class__.__name__
        ))
        # creating Configurations
        self.config = config
        # set global test mode variable
        gv.TEST_MODE = self.config["test-mode"]
        # validate configuration
        self.validate_config()
        # set global CONFIG variable
        gv.CONFIG = self.config
        # perform after init action
        self._after_init()
        # log self.configuration
        global_logger.debug("Scenario data: " + str(self.config))

    ## Validating config.
    # @param self Pointer to object.
    # @exception AutomationLibraryError("OPTION_NOT_FOUND")
    def validate_config(self):
        # first piece of data
        validate_data = [
            # common parameters
            ["test-mode", bool],
            ["time-limit", int],
            ["os-type", str, str, ["Windows", "Linux-deb", "Linux-rpm"]],
            ["standalone", bool],
        ]
        self.config.validate(validate_data)
        self._validate_specific_data()

    ## Execute tests.
    # @param self Pointer to object.
    def tests(self):
        l = LogFunc(message="Running tests")
        avaliable_tests = self._get_avaliable_tests()
        for name, test, standalone_only in avaliable_tests:
            if not self.config["standalone"] and standalone_only:
                global_logger.info(message="Omitting test", name=name)
                continue
            test()

    ## Execute scenario.
    # @param self Pointer to object.
    def execute(self):
        # make tests
        # if standalone, execute tests even if test-mode not set
        if self.config["standalone"]:
            self.tests()
            if self.config["test-mode"] is True:
                global_logger.info("Test mode completed successfully")
                return
        # otherwise, execute tests only if test-mode set
        else:
            if self.config["test-mode"] is True:
                self.tests()
                global_logger.info("Test mode completed successfully")
                return
        self._real()

    @classmethod
    ## Wrapper, which handles configuration creation, creation of current class
    #  object and execution it main execute method.
    # @param Cls Scenario class.
    def execute_wrapper(Cls):
        res = 1
        # execute scenario
        try:
            data = read_yaml(sys.argv[1])
            config = ScenarioConfiguration(data)
            cmd_args = bootstrap.parse_cmd_args(sys.argv[2:])
            config.add_cmd_args(cmd_args[1], True)
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
            bootstrap.set_debug_values(cmd_args[1])
            scenario = Cls(config)
            scenario.execute()
        # handle errors (ie log them and set return code)
        except Exception as err:
            res = Cls._handle_top_level_exception(err)
        else:
            res = 0
        return res


    # these functions can be (which is recommended) redefined in inherited
    # classes to provide necessary functionality.

    ## Method, which handles validation of scenario-specific data. It called
    #  in BaseScenario.validate_config() method after validation of common
    #  values like test-mode, time-limit, os-type and standalone.
    # @param self Pointer to object.
    def _validate_specific_data(self):
        pass

    ## Method, which is called right after main __init__() part, but before
    #  printing config property. This method should handle scenario-specific
    #  preparations for it execution, like set additional values, etc.
    #  STRONGLY not recommended to change state of object in this method!
    # @param self Pointer to object.
    def _after_init(self):
        pass

    ## Method, which return list of avaliable tests.
    # @param self Pointer to object.
    # @return List of tuples (test string name, function, standalone only flag).
    def _get_avaliable_tests(self):
        pass

    ## Real part of scenario execution, ie where actual work takes place.
    # @param self Pointer to object.
    def _real(self):
        pass


    # these methods is already implemented, so they could be used as-is in
    # inherited classes as well as they could be redefined.

    ## Method, which handles exceptions. This method SHOULD NOT throw exceptions
    #  in any case. This method should catch ANY exception (ie what inherited
    #  from Exception class) and return integer code. Default implementation of
    #  this method print any AutomationLibraryError via global_logger. Any
    #  non-AutomationLibraryError converted to AutomationLibraryError("UNKNOWN")
    #  and printed via global_logger.
    # @param err Exception object.
    # @return Integer value, which correspond to passed exception.
    @staticmethod
    def _handle_top_level_exception(err):
        res = 1
        if isinstance(err, AutomationLibraryError):
            global_logger.error(
                str(err), state="error",
            )
            res = err.num_code
        else:
            err = AutomationLibraryError("UNKNOWN", err)
            global_logger.error(
                str(err), state="error",
            )
            res = err.num_code
        return res
