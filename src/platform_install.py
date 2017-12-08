import sys
import shutil
import tempfile


from lib.common import bootstrap
from lib.common.config import *
from lib.utils import *
from lib.common.base_scenario import *
from lib.utils.const import ALL, SERVER, WEB_EXTENSION, CLIENT


class PlatformInstallScenario(BaseScenario):

    def _validate_specific_data(self):
        validate_data = [
            ["version", PlatformVersion],
            ["distr-folder",  StrPathExpanded],
            ["download-tmp-folder", StrPathExpanded],
            ["platform-modules", create_typed_list_checker(str),
             create_str_list_separate_builder(","),
             create_list_content_checker([ALL, SERVER, WEB_EXTENSION, CLIENT])],
        ]
        if self.config["os-type"] == "Windows":
            validate_data.append(["setup-folder", StrPathExpanded])
        else:
            self.config["setup-folder"] = ""
        self.config.validate(validate_data)
        if not set(self.config["platform-modules"]) \
           .isdisjoint(set([WEB_EXTENSION, ALL])):
            validate_data = [
                ["web-extension/path", StrPathExpanded],
            ]
            if self.config["os-type"] == "Windows":
                validate_data.append([
                    "web-extension/web-server", str, str,
                    ["IIS", "apache2.0", "apache2.2", "apache2.4"]
                ])
            else:
                validate_data.append([
                    "web-extension/web-server", str, str,
                    ["apache2.0", "apache2.2", "apache2.4"]
                ])
            self.config.validate(validate_data)

    def _after_init(self):
        self.config["distr-folder"] = os.path.join(
            self.config["distr-folder"],
            str(self.config["version"]),
        )
        if self.config["os-type"] == "Windows":
            from lib.win_utils.platform_updater import Platform1CUpdater
            self.Platform1CUpdater = Platform1CUpdater
        else:
            from lib.linux_utils.platform_updater import Platform1CUpdater
            self.Platform1CUpdater = Platform1CUpdater
        # Platform1C classes used temporary
        self.platform_installer = self.Platform1CUpdater(self.config)
        # set fields for future usage
        self.extracted_packages = list()
        self.extracted_files = list()
        self.distr_downloaded = False
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

    def _get_avaliable_tests(self):
        return [
            ("test-install-permissions",
             self.platform_installer.test_install_permissions, False),
            ("get-distr", self._get_distr, True),
            ("test-update", self.platform_installer.test_update, True),
        ]

    ## Copy files from source do destination. It is internally have retries.
    # @param self Pointer to object.
    # @param src Source of data (path).
    # @param dst Destination (path to folder).
    def _copy_files(self, src, dst):
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
    def _get_distr(self):
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
            self._copy_files(src, dst)
        else:
            global_logger.info("Distr found, omitting copy")
        # store update-type
        self.config["update-type"] = update_type
        # update global CONFIG variable
        gv.CONFIG = self.config
        self.distr_downloaded = True

    def _real(self):
        if not self.distr_downloaded:
                self._get_distr()
        self.platform_installer.update2()
        if not set(self.config["platform-modules"]) \
           .isdisjoint(set([WEB_EXTENSION, ALL])):
            self.platform_installer.copy_web_library2()


if __name__ == "__main__":
    bootstrap.main(PlatformInstallScenario.execute_wrapper,
                   os.path.basename(__file__)[0:-3])
