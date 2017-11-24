# coding: utf-8

import time


from .common.config import *
from .utils import *

class PlatformCtlScenario:
    ## Constructor.
    # @param self Pointer to object.
    # @param config lib::common::config::Configuration object.
    # @param action Action string ("start", "stop", "restart")
    # @param kwargs additional named args for config object.
    def __init__(self, config, action="start", **kwargs):
        l = LogFunc(message="initializing PlatformCtlScenario object")
        self.services = list()
        self.config = config
        self.action = action
        # validate configuration
        self.validate_config()
        # set global test mode variable
        gv.TEST_MODE = self.config["test-mode"]
        # fill list of services
        self.config["services"] = list()
        if self.config["server-role"] != "web":
            self.config["services"].append(self.config["service-1c"]["name"])
            self.config["services"].append(self.config["ras"]["name"])
        if self.config["server-role"] != "app":
            if self.config["os-type"] == "Windows":
                if self.config["web-server"].upper() == "IIS":
                    self.config["services"].append("IIS")
                else:
                    from .win_utils import get_apache_service_name
                    self.config["services"].append(get_apache_service_name())
            else:
                from .linux_utils import get_apache_service_name
                self.config["services"].append(get_apache_service_name())
        # log self.configuration
        global_logger.debug(
            "Scenario data: " + str(self.config)
        )
        # set global CONFIG variable
        gv.CONFIG = self.config

    ## Validating config.
    # @param self Pointer to object.
    # @exception AutomationLibraryError("OPTION_NOT_FOUND")
    def validate_config(self):

        def validate_web_servers(server):
            if self.config["os-type"] == "Windows" and \
               self.config["web-server"].lower() not in ["apache", "iis"]:
                global_logger.error(message="Incorrect web server. For Windows "
                                    "allowed web servers is 'apache' and 'iis'")
                return False
            elif self.config["os-type"] in ["Linux-deb", "Linux-rpm"] and \
                 self.config["web-server"].lower() not in ["apache"]:
                global_logger.error(message="Incorrect web server. For Linux "
                                    "allowed web servers is 'apache'")
                return False
            return True

        # build validate data
        validate_data = [
            ["server-role", str, str, ["all", "app", "web"]],
            ["test-mode", bool],
            ["try-count", int],
            ["timeout", int],
            ["time-limit", int],
            ["os-type", str, str, ["Windows", "Linux-deb", "Linux-rpm"]],
        ]
        if self.action != "start":
            validate_data += [
                ["clean-snccntx", bool],
                ["clean-pfl", bool],
                ["cluster-folder", StrPathExpanded],
                ["dumps-folder", StrPathExpanded],
            ]
        if self.config["server-role"] in ["app", "all"]:
            validate_data += [
                ["service-1c/name", str],
                ["ras/name", str],
            ]
        if self.config["server-role"] in ["web", "all"]:
            validate_data += [
                ["web-server", str, str, validate_web_servers],
            ]
        self.config.validate(validate_data)

    ## Wrapper for retry_func, which passes automatically self, timeout and
    #  try_count
    # @param self Pointer to object.
    # @param func Function to execute.
    # @param *args Positional arguments for func.
    # @param **kwargs Named arguments for func.
    def retry_self(self, func, *args, **kwargs):
        return retry_func(func, args=(self, ) + args, kwargs=kwargs,
                          timeout=self.config["timeout"],
                          try_count=self.config["try-count"])

    ## Wrapper for retry_func, which passes automatically timeout and try_count
    # @param self Pointer to object.
    # @param func Function to execute.
    # @param *args Positional arguments for func.
    # @param **kwargs Named arguments for func.
    def retry(self, func, *args, **kwargs):
        return retry_func(func, args=args, kwargs=kwargs,
                          timeout=self.config["timeout"],
                          try_count=self.config["try-count"])

    ## Preparation actions before actual start/stop platform.
    # @param self Pointer to object.
    def prepare(self):
        l = LogFunc(message="preparing to platform ctl action",
                    action=self.action)
        # choose service class
        ServiceCls = None
        if self.config["os-type"] == "Windows":
            from .win_utils.service import Service, IISService
            ServiceCls = Service
            IISServiceCls = IISService
        else:
            from .linux_utils.service import SystemdService
            ServiceCls = SystemdService
        # 1. Testing access to service control
        self.retry(ServiceCls.test_sc_permissions)
        # 2. Create ServiceCls objects
        self.services = list()
        for service_name in self.config["services"]:
            if self.config["os-type"] == "Windows" and \
               service_name.upper() == "IIS":
                self.services.append(IISServiceCls())
            else:
                self.services.append(ServiceCls(service_name))
            self.services[-1].connect()

    ## Start platform.
    # @param self Pointer to object.
    def start(self):
        l = LogFunc(message="starting 1C:Enterprise Platform")
        # If set test-mode, finish execution
        if self.config["test-mode"] is True:
            global_logger.info("Test mode completed successfully")
            return
        # 3. Start services
        for service in self.services:
            self.retry(service.start)
        # 4. Check services started after timeout
        global_logger.info(message="Give services time to start...")
        time.sleep(self.config["timeout"])
        for service in self.services:
            if not service.started:
                raise AutomationLibraryError("SERVICE_ERROR",
                                             "service not started",
                                             name=service.name)

    ## Stop platform.
    # @param self Pointer to object.
    def stop(self):
        l = LogFunc(message="stopping 1C:Enterprise Platform")
        # If set test-mode, finish execution
        if self.config["test-mode"] is True:
            global_logger.info("Test mode completed successfully")
            return
        # 3. Stop services gracefully
        for service in self.services:
            self.retry(service.stop)
        # 4. Check services stopped. If not, kill their processes.
        global_logger.info(message="Give services time to stop...")
        time.sleep(self.config["timeout"])
        for service in self.services:
            if service.started:
                service.stop(True)
                time.sleep(self.config["timeout"])
                if service.started:
                    raise AutomationLibraryError("SERVICE_ERROR",
                                                 "service not stopped",
                                                 name=service.name)

    ## Execute action.
    # @param self Pointer to object.
    # @param action Action string ("start", "stop", "restart")
    def execute(self, action=None):
        if action is None:
            action = self.action
        self.prepare()
        if action == "start":
            self.start()
        elif action == "stop":
            self.stop()
        elif action == "restart":
            self.stop()
            self.start()
        else:
            raise AutomationLibraryError(
                "UNKNOWN", Exception("Unknown action for PlatformCtlScenario"),
                action=action
            )
