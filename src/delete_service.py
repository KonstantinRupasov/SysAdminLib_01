import sys
import os


from lib.common import bootstrap
from lib.common.errors import *
from lib.common.logger import *
from lib.utils import *
from lib.utils.cmd import run_cmd
from lib.common import global_vars as gv
from lib.common.config import *
from lib.common.base_scenario import BaseScenario


class DeleteServiceScenario(BaseScenario):

    def _after_init(self):
        if self.config["os-type"] == "Windows":
            from lib.win_utils import service
        else:
            from lib.linux_utils import service
        self.service_module = service

    def _service_started(self):
        srvc = self.service_module.Service(self.config["name"])
        if srvc.connect(ignore_errors=True):
            if srvc.started:
                raise AutomationLibraryError(
                    "SERVICE_ERROR", "service running",
                    service=self.config["name"]
                )

    def _get_avaliable_tests(self):
        return [
            ("service-started", self._service_started, False),
        ]

    def _validate_specific_data(self):
        validate_data = [
            ["name", str],
        ]
        self.config.validate(validate_data)

    def _real(self):
        self.service_module.delete_service(self.config["name"])


if __name__ == "__main__":
    bootstrap.main(DeleteServiceScenario.execute_wrapper,
                   os.path.basename(__file__)[0:-3])
