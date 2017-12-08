# coding: utf-8

import time
import shutil
import os


from .win_utils import *
from .permissions import *
from .service import *
from ..utils import *
from ..utils.const import ALL, SERVER, WEB_EXTENSION, CLIENT


class Platform1CUpdater:
    ## Constructor.
    # @param self Pointer to object.
    # @param config common::config::Configuration object. If omitted, then
    #  common::global_vars::CONFIG used.
    def __init__(self, config=gv.CONFIG, **kwargs):
        self.config = config

    ## Testing service control permissions.
    # @param self Pointer to object.
    def test_sc_permissions(self):
        # if server role is SERVER or ALL, check access to service control
        # and correctness of user name and passwords
        if not set(self.config["platform-modules"])\
           .isdisjoint(set([SERVER, ALL])):
            Service.test_sc_permissions(
                self.config["service-1c"]["login"],
                self.config["service-1c"]["password"]
            )
            Service.test_sc_permissions(
                self.config["ras"]["login"],
                self.config["ras"]["password"]
            )

    ## Testing installation permissions.
    # @param self Pointer to object.
    def test_install_permissions(self):
        l = LogFunc(message="install permission test")
        # this disabled cuz when this method called we dont know update type
        # if self.config["update-type"] == "copy":
        #     pass
        # else:
        #     if not check_always_elevated_update() and not test_is_admin():
        #         raise AutomationLibraryError("WIN_INSTALL_PERM_DENIED")
        if not check_always_elevated_update() and not test_is_admin():
            raise AutomationLibraryError("WIN_INSTALL_PERM_DENIED")

    ## Install services.
    # @param self Pointer to object.
    def install_services(self):
        l = LogFunc(message="Installing services")
        install_service_1c(
            self.config["service-1c"]["name"], self.config["setup-folder"],
            self.config["service-1c"]["login"],
            self.config["service-1c"]["password"],
            self.config["cluster-folder"],
        )
        install_ras(
        self.config["ras"]["name"], self.config["setup-folder"],
            self.config["ras"]["login"],
            self.config["ras"]["password"]
        )

    ## Test update (ie is packages is correct, can be installed etc).
    # @param self Pointer to object.
    def test_update(self):
        pass

    def test_old_version(self):
        # compare old-version
        config_old_ver = self.config["old-version"]
        if config_old_ver != PlatformVersion(None):
            # get installed platform version
            actual_old_ver = get_installed_platform_version(
                self.config
            )
            # if cannot get installed platform version, raise exception
            if actual_old_ver == "":
                raise AutomationLibraryError("OLD_VERSION_NOT_DETECTED")
            # if old versions doesn't match. raise exception
            elif actual_old_ver != config_old_ver:
                raise AutomationLibraryError("OLD_VERSION_DOESNT_MATCH",
                                             actual_old_ver,
                                             config_old_ver)

    ## Uninstall old version of platform.
    # @param self Pointer to object.
    def uninstall_old(self):
        l = LogFunc(message="Uninstall old version of platform")
        uninstalled = False
        # if ragent.exe found in setup-folder, assume that previous version
        # was installed via copy
        if os.path.exists(os.path.join(
                self.config["setup-folder"], "ragent.exe")):
            global_logger.debug(message="Old version installed via copy",
                                path=os.path.exists(os.path.join(
                                    self.config["setup-folder"], "ragent.exe")
                                ))
            uninstalled = self._copy_uninstall()
        # if ragent.exe found in setup-folder/bin, assume that previous
        # version was installed via MSI
        elif os.path.exists(os.path.join(self.config["setup-folder"], "bin",
                                         "ragent.exe")):
            old_version = get_installed_platform_version(self.config)
            global_logger.debug(
                message="Old version installed via MSI installer")
            uninstalled = self._setup_exe_uninstall()
        # if ragent.exe not found, assume, that there is no conflicting previous
        # version installed, report warning
        else:
            uninstalled = False
        if not uninstalled:
            if self.config["old-version"] == "":
                global_logger.info(
                    "Cannot find old installation in current "
                    "setup-folder. You can safely ignore this message if "
                    "you do not have anything installed in this folder, "
                    "otherwise report to developer"
                )
            else:
                raise AutomationLibraryError(
                    "INSTALL_ERROR", "Cannot uninstall currently installed in "
                    "setup-folder 1C Platform"
                )

    ## Uninstall "copy" installation
    # @param self Pointer to object.
    def _copy_uninstall(self):
        # first: unregister dlls
        try:
            regsvr_unregister_dll(os.path.join(self.config["setup-folder"],
                                               "comcntr.dll"))
        except:
             pass
        try:
            regsvr_unregister_dll(os.path.join(self.config["setup-folder"],
                                               "radmin.dll"))
        except:
             pass
         # second: remove folder
        if os.path.exists(self.config["setup-folder"]):
            shutil.rmtree(self.config["setup-folder"], ignore_errors=True)
        if not os.path.exists(self.config["setup-folder"]):
            os.makedirs(self.config["setup-folder"], exist_ok=True)
        return True

    ## Uninstall "setup" installation
    # @param self Pointer to object.
    def _setup_exe_uninstall(self):
        try:
            # retrieving list of installed 1C:Enterprise versions
            csv = execute_wmic_get_command(
                "product",
                "Name like '%1C:%' AND InstallLocation like '%{}%'"
                " AND NOT Name like '%Ring%' AND NOT Name like '%License%'"
                .format(os.path.join(self.config["setup-folder"], "")
                        .replace("\\", "\\\\")),
                "Name"
            )
        except Exception as err:
            return False
        # parsing returned CSV
        name_filed_position = 1
        for col in range(0, len(csv[0])):
            if col == "Name":
                name_filed_position = col
        # uninstall all that match requested version
        for row in csv[1:]:
            global_logger.info(message="Uninstall platform",
                               product_name=row[name_filed_position])
            res = run_cmd("wmic product where \"Name='{}'\" call uninstall"
                          .format(row[name_filed_position]), shell=True)
            global_logger.debug(res)
            if len(res.stderr.strip(b"\r\n ")) == 0 and res.returncode == 0:
                return True
            else:
                return False

    ## Update platform.
    # @param self Pointer to object.
    def update(self):
        l = LogFunc(message="Updating 1C:Enterprise Platform")
        # 0. Remove old installation of platform.
        self.uninstall_old()
        # 0.1. Creating cluster folder, if doesn't exist.
        if not os.path.exists(self.config["cluster-folder"]):
            os.makedirs(self.config["cluster-folder"], exist_ok=True)
        run_cmd("cacls {} /E /G {}:f".format(
            self.config["cluster-folder"],self.config["service-1c"]["login"]
        ), shell=True)
        # 1. Install new version.
        if self.config["update-type"] == "copy":
            self._copy_install()
        else:
            self._setup_exe_install()
        self._validate_installation()
        # 2. Install services.
        if not set(self.config["platform-modules"])\
           .isdisjoint(set([SERVER, ALL])):
            self.install_services()
        self.clean_temps()
        # 3. Copy web-extension.
        if not set(self.config["platform-modules"]) \
           .isdisjoint(set([WEB_EXTENSION, ALL])):
            copy_web_library(self.config["web-library"]["path"],
                             self.config["setup-folder"])

    def update2(self):
        l = LogFunc(message="Updating 1C:Enterprise Platform")
        if self.config["update-type"] == "copy":
            self._copy_install()
        else:
            self._setup_exe_install()
        self._validate_installation()

    def copy_web_library2(self):
        dll_table = {
            "IIS": "wsisapi.dll",
            "apache2.0": "wsapch2.dll",
            "apache2.2": "wsap22.dll",
            "apache2.4": "wsap24.dll",
        }
        head, tail = os.path.split(self.config["web-extension/path"])
        if not os.path.exists(head):
            os.makedirs(head)
        src = os.path.join(
            self.config["setup-folder"],
            dll_table[self.config["web-extension/web-server"]]
        )
        # if library not found in setup-folder, try to find in bin
        # if still bot found, raise and exception
        if not os.path.exists(src):
            src = os.path.join(
                self.config["setup-folder"], "bin",
                dll_table[self.config["web-extension/web-server"]]
            )
            if not os.path.exists(src):
                raise AutomationLibraryError(
                    "INSTALLATION_ERROR", "Cannot find web extension library",
                    setup_folder=self.config["setup-folder"],
                    library_name=dll_table[
                        self.config["web-extension/web-server"]
                    ]
                )
        try:
            shutil.copy2(src, self.config["web-extension/path"])
        except shutil.SameFileError:
            pass


    ## Setup via "copy".
    # @param self Pointer to object.
    def _copy_install(self):
        l = LogFunc(message="Install platform via copy")
        if not os.path.exists(self.config["setup-folder"]):
            os.makedirs(self.config["setup-folder"])
        res = run_cmd([
            "copy", os.path.join(self.config["download-tmp-folder"], "*"),
            os.path.join(self.config["setup-folder"], "")
        ], shell=True)
        global_logger.debug(res.stdout)
        print(self.config["platform-modules"])
        if ALL in self.config["platform-modules"] or \
           SERVER in self.config["platform-modules"]:
            regsvr_register_dll(os.path.join(self.config["setup-folder"],
                                             "comcntr.dll"))
            regsvr_register_dll(os.path.join(self.config["setup-folder"],
                                             "radmin.dll"))


    ## Setup via "setup.exe"
    # @param self Pointer to object.
    def _setup_exe_install(self):
        l = LogFunc(message="Install platform via setup.exe")
        # 1. Building setup.exe path.
        setup_exe_name = "setup.exe"
        setup_exe_path = os.path.join(self.config["download-tmp-folder"],
                                      setup_exe_name)
        # 2. Remove download location data from file's ADS.
        run_cmd("echo.>\"{}:Zone.Identifier\"".format(setup_exe_path),
                shell=True)
        # 3. Gather installation data.
        server = 1 if not set(self.config["platform-modules"]) \
                 .isdisjoint(set([SERVER, ALL])) else 0
        web_ext = 1 if not set(self.config["platform-modules"]) \
                  .isdisjoint(set([WEB_EXTENSION, ALL])) else 0
        client = 1 if not set(self.config["platform-modules"])\
                 .isdisjoint(set([CLIENT, ALL])) else 0
        if "languages" in self.config:
            langs = self.config["languages"].upper()
        else:
            langs = "EN"
        components = "DESIGNERALLCLIENTS={} THINCLIENT=0" \
            " WEBSERVEREXT={} SERVER={} CONFREPOSSERVER=0 CONVERTER77=0 " \
            " SERVERCLIENT={} LANGUAGES={}".format(client, web_ext, server,
                                                   server, langs)
        # 4. Run installation.
        res = run_cmd("\"{}\" /S INSTALLDIR=\"{}\" {}".format(
            setup_exe_path, self.config["setup-folder"], components
        ), shell=True)
        global_logger.debug(res)
        # 5. Waiting for end of installation.
        while len(get_processes_id_by_name("msiexec")) > 1:
            time.sleep(5)
            global_logger.debug(
                msiexec_procs=len(get_processes_id_by_name("msiexec")),
            )
        if len(get_processes_id_by_name("msiexec")) > 1:
            raise AutomationLibraryError(
                "INSTALLATION_ERROR",
                "found too many msiexec processes, installation may be still in progress"
            )
        # 7. Add \bin to setup-folder
        self.config["setup-folder"] = os.path.join(self.config["setup-folder"],
                                                   "bin")

    def _validate_installation(self):

        def check_files_presence(path, file_list):
            if not os.path.exists(path):
                raise AutomationLibraryError(
                        "INSTALL_ERROR", "Folder not found", file=path
                    )
            for f in file_list:
                if f not in os.listdir(path):
                    raise AutomationLibraryError(
                        "INSTALL_ERROR", "File not found", file=f
                    )

        l = LogFunc(message="Validating installation")
        test_files = {
            "common": [],
            CLIENT: ["1cv8.exe", "1cv8c.exe"],
            SERVER: ["ragent.exe", "rmngr.exe", "rphost.exe", "ras.exe",
                     "rac.exe"],
            WEB_EXTENSION: ["wsisapi.dll"],
        }

        check_files_presence(self.config["setup-folder"], test_files["common"])
        if CLIENT in self.config["platform-modules"]:
            check_files_presence(self.config["setup-folder"],
                                 test_files[CLIENT])
        if SERVER in self.config["platform-modules"]:
            check_files_presence(self.config["setup-folder"],
                                 test_files[SERVER])
        if WEB_EXTENSION in self.config["platform-modules"]:
            check_files_presence(self.config["setup-folder"],
                                test_files[WEB_EXTENSION])
        if ALL in self.config["platform-modules"]:
            check_files_presence(self.config["setup-folder"],
                                 test_files[CLIENT])
            check_files_presence(self.config["setup-folder"],
                                 test_files[SERVER])
            check_files_presence(self.config["setup-folder"],
                                test_files[WEB_EXTENSION])

    ## Clean temps (snccntx* and *.pfl).
    # @param self Pointer to object.
    def clean_temps(self):
        l = LogFunc(message="cleaning temps")
        srvinfo = self.config["cluster-folder"]
        # cleaning cluster-folder/reg_1541/snccntx*
        if self.config["clean-snccntx"]:
            reg_1541 = os.path.join(os.path.join(self.config["cluster-folder"],
                                                 "reg_1541"))
            if not os.path.exists(reg_1541):
                return
            listdir = os.listdir(reg_1541)
            for item in listdir:
                match = re.search("snccntx", item)
                if match is not None:
                    shutil.rmtree(
                        os.path.join(reg_1541, match.string),
                        ignore_errors=True
                    )
        # cleaning cluster-folder/*.pfl
        if self.config["clean-pfl"]:
            if not os.path.exists(srvinfo):
                return
            listdir = os.listdir(srvinfo)
            for item in listdir:
                match = re.search(".*\\.pfl", item)
                if match is not None:
                    os.remove(os.path.join(srvinfo, match.string))
