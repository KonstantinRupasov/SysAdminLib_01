import sys
import shutil
import tempfile


from lib.common import bootstrap
from lib.common.config import *
from lib.utils import *
from lib.common.base_scenario import *
from lib.crossplatform_utils import *


class PlatformRemoveScenario(BaseScenario):

    def _validate_specific_data(self):
        validate_data = [
            ["version", PlatformVersion],
        ]
        if self.config["os-type"] == "Windows":
            validate_data.append(["setup-folder", StrPathExpanded])
        else:
            self.config["setup-folder"] = ""
        self.config.validate(validate_data)
        # logic check
        if self.config["os-type"] == "Windows":
            if self.config["version"] == "" \
               and self.config["setup-folder"] == "":
                raise AutomationLibraryError(
                    "ARGS_ERROR", "Both version and setup folder not specified,"
                    " which is prohibited"
                )

    def _after_init(self):
        # temp WORKAROUND
        self.config["old-version"] = self.config["version"]
        if self.config["os-type"] == "Windows":
            from lib.win_utils.platform_updater import Platform1CUpdater
            self.Platform1CUpdater = Platform1CUpdater
        else:
            from lib.linux_utils.platform_updater import Platform1CUpdater
            self.Platform1CUpdater = Platform1CUpdater
        self.platform_remover = self.Platform1CUpdater(self.config,
                                                       uninstall_only=True)
        if self.config["os-type"] == "Windows":
            from lib.win_utils import service
        else:
            from lib.linux_utils import service
        self.service_module = service

    def _check_cluster_started(self):
        folder = self.config["setup-folder"] \
                 if self.config["os-type"] == "Windows" else ""
        num_of_procs = number_of_ragent_processes_running(folder)
        if num_of_procs > 0:
            raise AutomationLibraryError("INSTALL_ERROR",
                                         "cluster processes is running")

    def _get_avaliable_tests(self):
        return [
            ("check-old-version", self.platform_remover.test_old_version,
             False),
            ("check-cluster-started", self._check_cluster_started, False),
        ]

    def _real(self):
        self.platform_remover.uninstall_old()


if __name__ == "__main__":
    bootstrap.main(PlatformRemoveScenario.execute_wrapper,
                   os.path.basename(__file__)[0:-3])
