import sys
import os


from lib.common import bootstrap
from lib.common.errors import *
from lib.common.logger import *
from lib.utils import *
from lib.utils.cmd import run_cmd
from lib.common import global_vars as gv
from lib.common.config import *
from lib.common.base_scenario import *


class CreateRagentServiceScenario(BaseScenario):

    def _after_init(self):
        if self.config["os-type"] == "Windows":
            from lib.win_utils import service
        else:
            from lib.linux_utils import service
        self.service_module = service

    def _validate_specific_data(self):
        # first piece of data
        validate_data = [
            # specific paramenters
            ["name", str],
            ["description", str],
            ["port", int],
            ["regport", int],
            ["range", str, str, dyn_range_checker],
            ["username", str],
            ["cluster-folder", StrPathExpanded],
            ["setup-folder", StrPathExpanded],
            ["cluster-debug", bool]
        ]
        self.config.validate(validate_data)
        if self.config["os-type"] == "Windows":
            validate_data = [["password", str], ]
        else: # WORKAROUND
            self.config["password"] = ""
        self.config.validate(validate_data)

    def _check_setup_folder(self):
        # only check that ragent is there
        ragent_name = "ragent" if self.config["os-type"] != "Windows" else \
                                                            "ragent.exe"
        if not os.path.exists(os.path.join(self.config["setup-folder"],
                                                       ragent_name)):
            raise AutomationLibraryError(
                "ARGS_ERROR", "ragent not found in setup-folder",
                setup_folder=self.config["setup-folder"]
            )

    def _check_data_not_used(self):
        if not self.service_module.can_create_1c_cluster_service(
                self.config["name"], self.config["port"],
                self.config["regport"], dyn_range_parser(self.config["range"]),
                self.config["cluster-folder"]
        ):
            raise AutomationLibraryError(
                "ARGS_ERROR", "ragent service with specified parameters is "
                "already exists", name=self.config["name"],
                port=self.config["port"], regport=self.config["regport"],
                range=self.config["range"],
                cluster_folder=self.config["cluster-folder"]
            )

    def _get_avaliable_tests(self):
        return [
            ("test-sc-permissions",
             self.service_module.Service.test_sc_permissions, False),
            ("check-setup-folder", self._check_setup_folder, True),
            ("check-data-not-used", self._check_data_not_used, True),
        ]

    def _real(self):
        srv1cv8 = self.service_module.install_service_1c(
            self.config["name"], self.config["setup-folder"],
            self.config["username"], self.config["password"],
            self.config["cluster-folder"], self.config["port"],
            self.config["regport"], self.config["range"],
            self.config["cluster-debug"], self.config["description"]
        )
        # if cluster folder doesn't exist, create it and set ownership
        if not os.path.exists(self.config["cluster-folder"]):
            os.makedirs(self.config["cluster-folder"], exist_ok=True)
        if self.config["os-type"] == "Windows":
            run_cmd("cacls {} /E /G {}:f".format(
                self.config["cluster-folder"],self.config["username"]
            ), shell=True)
        else:
            run_cmd(["chown", "-R", str(self.config["username"]),
                     self.config["cluster-folder"]])


def dyn_range_parser(str_range):
    ports = []
    try:
        subranges = str_range.split(",")
        for subrange in subranges:
            parts = subrange.split(":")
            if len(parts) < 2:
                ports.append(int(parts[0]))
            else:
                ports += list(range(int(parts[0]), int(parts[1])+1))
    except:
        raise ValueError("Incorrect dynamic range")
    return ports


def dyn_range_checker(str_range):
    try:
        dyn_range_parser(str_range)
        return True
    except:
        return False


if __name__ == "__main__":
    bootstrap.main(CreateRagentServiceScenario.execute_wrapper,
                   os.path.basename(__file__)[0:-3])
