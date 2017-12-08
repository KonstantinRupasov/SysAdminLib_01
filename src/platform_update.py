#!/usr/bin/python3
# coding: utf-8
import sys
import shutil
import tempfile


from lib.common import bootstrap
from lib.common.config import *
from lib.utils import *


class PlatformUpdateScenario:
    ## Constructor.
    # @param self Pointer to object.
    # @param config lib::common::config::Configuration object.
    # @param kwargs additional named args for config object.
    def __init__(self, config, **kwargs):
        self.extracted_packages = list()
        self.extracted_files = list()
        self.distr_downloaded = False
        self.Platform1CUpdater = None
        self.platform_updater = None
        l = LogFunc(message="initializing PlatformUpdateScenario object")
        self.config = config
        # set global test mode variable
        gv.TEST_MODE = self.config["test-mode"]
        # extracting platform versions
        self.config["new-version"] = PlatformVersion(
            self.config["new-version"]
        )
        self.config["old-version"] = PlatformVersion(
            self.config["old-version"]
        )
        # building distr-folder
        self.config["distr-folder"] = os.path.join(
            self.config["distr-folder"],
            str(self.config["new-version"]),
        )
        # getting OS-specific utils module
        if self.config["os-type"] == "Windows":
            from lib import win_utils
            self.spec_utils_module = win_utils
        elif self.config["os-type"] == "Linux-deb":
            from lib.linux_utils import deb
            self.spec_utils_module = deb
        elif self.config["os-type"] == "Linux-rpm":
            from lib.linux_utils import rpm
            self.spec_utils_module = rpm
        else:
            raise AutomationLibraryError("ARGS_ERROR", "wrong os-type",
                                         value=self.config["os-type"])
        # getting archive name
        self.config["setup-distr-archive"] \
            = self.spec_utils_module.ARCHIVE64_DISTR_NAME \
            if self.config["arch"] == 64 else \
            self.spec_utils_module.ARCHIVE32_DISTR_NAME
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
            # ["server-role", str, str, ["all", "app", "web"]],
            ["platform-modules", create_typed_list_checker(str),
             create_str_list_separate_builder(","),
             create_list_content_checker(["all", "app", "web", "client"])],
            ["test-mode", bool],
            # ["try-count", int],
            # ["timeout", int],
            ["time-limit", int],
            ["os-type", str, str, ["Windows", "Linux-deb", "Linux-rpm"]],
            ["clean-snccntx", bool],
            ["clean-pfl", bool],
            ["cluster-folder", StrPathExpanded],
            ["distr-folder", StrPathExpanded],
            ["download-tmp-folder", StrPathExpanded],
            ["standalone", bool]
        ]
        self.config.validate(validate_data)
        # ie if app or all in platform-modules
        if not set(self.config["platform-modules"])\
           .isdisjoint(set(["app", "all"])):
            validate_data += [
                ["service-1c/name", str],
                ["service-1c/login", str],
                ["ras/name", str],
                ["ras/login", str],
                ["ras/port", int],
                ["ras/path", StrPathExpanded],
            ]
            if self.config["os-type"] == "Windows":
                validate_data += [
                    ["service-1c/password", str],
                    ["ras/password", str],
                ]
        self.config.validate(validate_data)

    ## Copy files from source do destination. It is internally have retries.
    # @param self Pointer to object.
    # @param src Source of data (path).
    # @param dst Destination (path to folder).
    def copy_files(self, src, dst):
        l = LogFunc(message="copy distr", src=src, dst=dst)
        # try copy try-count times
        for attempt in range(self.config["try-count"] - 1, -1, -1):
            # execute copy
            res = None
            try:
                if self.config["os-type"] == "Windows":
                    res = run_cmd(["copy", src, dst], shell=True)
                else:
                    res = run_cmd(" ".join(["cp", "-r", src, dst]),
                                  shell=True)
            # if exception raised or returncode is not 0, then try again
            # if attempts left, else raise exception
            except Exception as err:
                if attempt > 0:
                    global_logger.info("Retrying,attempts_left={}"
                                       .format(attempt), error=str(err))
                else:
                    raise
            else:
                if res.returncode != 0:
                    if attempt > 0:
                        global_logger.info("Retrying,attempts_left={}"
                                           .format(attempt),
                                           error=res.stderr)
                    else:
                        raise AutomationLibraryError("FILE_COPY_ERROR", src, dst,
                                                     res.stderr)
            global_logger.debug(res.stdout)
            return

    ## Obtain distr.
    # @param self Pointer to object.
    def get_distr(self):
        l = LogFunc(message="obtaining distr")
        # detecting installation type
        update_type = detect_installation_type(
            self.config["setup-distr-archive"],
            self.config["distr-folder"]
        )
        # building paths for self.copy_files
        src = os.path.join(self.config["distr-folder"], "*")
        # append slash to the end of dst
        dst = os.path.join(self.config["download-tmp-folder"], "")
        # compare hashes of src and dst and, if they doesn't match, perform
        # copy
        if not os.path.exists(dst) \
           or compute_recursive_hash([dst, ]) \
           != compute_recursive_hash([self.config["distr-folder"], ]):
            if os.path.exists(dst):
                shutil.rmtree(dst, ignore_errors=True)
            if not os.path.exists(dst):
                os.makedirs(dst)
            self.copy_files(src, dst)
        else:
            global_logger.info("Distr found, omitting copy")
        # store update-type
        self.config["update-type"] = update_type
        # update global CONFIG variable
        gv.CONFIG = self.config
        self.distr_downloaded = True

    ## Check, if services started.
    # @param self Pointer to object.
    def check_services_state(self):
        services_names = [self.config["service-1c"]["name"],
                          self.config["ras"]["name"]]
        # choose service class
        ServiceCls = None
        if self.config["os-type"] == "Windows":
            from lib.win_utils.service import Service
            ServiceCls = Service
        else:
            from lib.linux_utils.service import SystemdService
            ServiceCls = SystemdService
        # 1. Check access to service control
        ServiceCls.test_sc_permissions
        # 2. Creating ServiceCls objects and trying to connect to them.
        services = list()
        for service_name in services_names:
            try:
                service = ServiceCls(service_name)
                service.connect()
                services.append(service)
            except Exception:
                pass
        # 3. If at least one service started, raise error.
        for service in services:
            if service.started:
                raise AutomationLibraryError("INSTALL_ERROR", "service started",
                                             name=service.name)

    ## Check, if processes with image file from setup-folder started
    def check_processes_state(self):
        ragent_path = os.path.join(self.config["setup-folder"], "ragent")
        ragent_procs = list()
        if self.config["os-type"] == "Windows":
            from lib.win_utils import get_processes_id_by_name
            ragent_procs = get_processes_id_by_name(
                "ragent.exe",
                repr(self.config["setup-folder"])[1:-1]
            )
        else:
            from lib.linux_utils import get_processes_id_by_name
            ragent_procs = get_processes_id_by_name(ragent_path)
        if len(ragent_procs) > 0:
            raise AutomationLibraryError("INSTALL_ERROR",
                                         "processes is runnining")
        # Check, that no one use cluster-folder
        if self.config["cluster-folder"] != "":
            cluster_folder_users = get_processes_id_by_name(
                "ragent", self.config["cluster-folder"]
            )
            if len(cluster_folder_users) > 0:
                raise AutomationLibraryError(
                    "INSTALL_ERROR",
                    "cluster folder used by processes",
                    procs=[proc[0] for proc in cluster_folder_users]
                )

    def _check_cluster_started(self):
        self.check_services_state()
        self.check_processes_state()

    def _check_cluster_folder_not_used(self):
        pass

    def tests(self):
        l = LogFunc(message="Running tests")
        # (name, function, standalone_only)
        avaliable_tests = [
            ("cluster-started", self._check_cluster_started, True),
            ("cluster-folder-not-used", self._check_cluster_folder_not_used,
             False),
            ("test-install-permissions",
             self.platform_updater.test_install_permissions, False),
            ("test-sc-permissions",
             self.platform_updater.test_sc_permissions, False),
            ("test-old-version", self.platform_updater.test_old_version, False),
            # this 2 goes last cuz they can take much time
            ("get-distr", self.get_distr, True),
            # this test is depend on previous, cuz what we should test,
            # if there is no distr, right?
            ("test-update", self.platform_updater.test_update, True),
        ]
        # execute tests
        for name, test, standalone_only in avaliable_tests:
            if not self.config["standalone"] and standalone_only:
                global_logger.info(message="Omitting test", name=name)
                continue
            test()

    ## Execute scenario.
    # @param self Pointer to object.
    def execute(self):
        # 1. Create and set up Platform1CUpdater object.
        self.Platform1CUpdater = None
        if self.config["os-type"] == "Windows":
            from lib.win_utils.platform_updater import Platform1CUpdater
            self.Platform1CUpdater = Platform1CUpdater
        else:
            from lib.linux_utils.platform_updater import Platform1CUpdater
            self.Platform1CUpdater = Platform1CUpdater
        self.platform_updater = self.Platform1CUpdater(self.config)
        # if standalone, run both test mode and real update
        if self.config["standalone"]:
            # make tests
            self.tests()
            if self.config["test-mode"] is True:
                global_logger.info("Test mode completed successfully")
                return
            # perform installation
            if not self.distr_downloaded:
                self.get_distr()
            self.platform_updater.update()
        else:
            # here, if test-mode set, run ONLY tests
            if self.config["test-mode"] is True:
                self.tests()
                global_logger.info("Test mode completed successfully")
                return
            # if test mode not set, run update without tests
            if not self.distr_downloaded:
                self.get_distr()
            self.platform_updater.update()




## Wrapper for scenario execution.
# @return Last error code (0 if no errors occurred).
def platform_update_scenario():
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
        scenario = PlatformUpdateScenario(config)

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
    bootstrap.main(platform_update_scenario,
                   os.path.basename(__file__)[0:-3])
