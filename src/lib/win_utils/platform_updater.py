# coding: utf-8

import time

from .win_utils import *
from .permissions import *
from .service import Service


class Platform1CUpdater:
    ## Constructor.
    # @param self Pointer to object.
    # @param config common::config::Configuration object. If omitted, then
    #  common::global_vars::CONFIG used.
    def __init__(self, config=gv.CONFIG, **kwargs):
        self.config = config

    ## Testing installation permissions.
    # @param self Pointer to object.
    def test_permissions(self):
        l = LogFunc(message="permission test")
        # if server role is "app" or "all", check access to service control
        # and correctness of user name and passwords
        if self.config["server-role"] in ["app", "all"]:
            Service.test_sc_permissions(
                self.config["service-1c"]["login"],
                self.config["service-1c"]["password"]
            )
            Service.test_sc_permissions(
                self.config["ras"]["login"],
                self.config["ras"]["password"]
            )
        # if update type is "setup", then check Administrator privilege and
        # AlwaysInstallElevated key.
        if self.config["update-type"] == "copy":
            pass
        else:
            if not check_always_elevated_update() and not test_is_admin():
                raise AutomationLibraryError("WIN_INSTALL_PERM_DENIED")

    ## Install services.
    # @param self Pointer to object.
    def install_services(self):
        l = LogFunc(message="Installing services")
        # install ragent service
        srv1cv8 = Service(self.config["service-1c"]["name"])
        if srv1cv8.connect(True):
            srv1cv8.delete()
            srv1cv8.disconnect()
        # building command
        cmd = "\"{}\" -srvc -agent -regport 1541 -port 1540 -range 1560:1591" \
              " -d {} {}".format(
                  os.path.join(self.config["setup-folder"], "ragent.exe"),
                  self.config["cluster-folder"],
                  "-debug" if self.config["cluster-debug"] else ""
              )
        srv1cv8.create(
            cmd,
            self.config["service-1c"]["login"],
            self.config["service-1c"]["password"]
        )
        # install RAS service
        srv1cv8_ras = Service(self.config["ras"]["name"])
        if srv1cv8_ras.connect(True):
            srv1cv8_ras.delete()
            srv1cv8_ras.disconnect()
        srv1cv8_ras.create(
            "\"{}\" cluster --service --port={}".format(
                os.path.join(self.config["setup-folder"], "ras.exe"),
                self.config["ras"]["port"]
            ),
            self.config["ras"]["login"],
            self.config["ras"]["password"]
        )
        srv1cv8_ras.connect()
        # remove file, created by SC utility
        if os.path.exists("delete"):
            os.remove("delete")

    ## Test update (ie is packages is correct, can be installed etc).
    # @param self Pointer to object.
    def test_update(self):
        l = LogFunc(message="Testing update")
        # check access permissions
        self.test_permissions()
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
        l = LogFunc(message="uninstalling old version of platform")
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
            global_logger.info(message="Uninstalling platform",
                               product_name=row[name_filed_position])
            res = run_cmd("wmic product where \"Name='{}'\" call uninstall"
                          .format(row[name_filed_position]), shell=True,
                          timeout=self.config["timeout"])
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
        ), shell=True, timeout=self.config["timeout"])
        # 1. Install new version.
        if self.config["update-type"] == "copy":
            self._copy_install()
        else:
            self._setup_exe_install()
        # 2. Install services.
        if self.config["server-role"] in ["all", "app"]:
            self.install_services()
        self.clean_temps()
        # 3. Copy web-extension.
        if self.config["server-role"] in ["all", "web"]:
            copy_web_library(self.config["web-library"]["path"],
                             self.config["setup-folder"])

    ## Setup via "copy".
    # @param self Pointer to object.
    def _copy_install(self):
        l = LogFunc(message="Installing platform via copy")
        res = run_cmd([
            "copy", os.path.join(self.config["download-tmp-folder"], "*"),
            os.path.join(self.config["setup-folder"], "")
        ], shell=True)
        global_logger.debug(res.stdout)

    ## Setup via "setup.exe"
    # @param self Pointer to object.
    def _setup_exe_install(self):
        l = LogFunc(message="Installing platform via setup.exe")
        # 1. Building setup.exe path.
        setup_exe_name = "setup.exe"
        setup_exe_path = os.path.join(self.config["download-tmp-folder"],
                                      setup_exe_name)
        # 2. Remove download location data from file's ADS.
        run_cmd("echo.>\"{}:Zone.Identifier\"".format(setup_exe_path),
                shell=True)
        # 3. Gather installation data.
        server = 1 if self.config["server-role"] in ["all", "app"] else 0
        web_ext = 1 if self.config["server-role"] in ["all", "web"] else 0
        if "languages" in self.config:
            langs = self.config["languages"].upper()
        else:
            langs = "EN"
        components = "DESIGNERALLCLIENTS={} THINCLIENT=0" \
            " WEBSERVEREXT={} SERVER={} CONFREPOSSERVER=0 CONVERTER77=0 " \
            " SERVERCLIENT=0 LANGUAGES={}".format(server, web_ext, server,
                                                  langs)
        # 4. Run installation.
        res = run_cmd("\"{}\" /S INSTALLDIR=\"{}\" {}".format(
            setup_exe_path, self.config["setup-folder"], components
        ), shell=True, timeout=self.config["timeout"])
        global_logger.debug(res)
        # 5. Waiting for end of installation.
        i = 0
        while (i < self.config["timeout"]) and len(
                get_processes_id_by_name("msiexec")) > 1:
            time.sleep(5)
            i += 5
            global_logger.debug(
                msiexec_procs=len(get_processes_id_by_name("msiexec")),
                time_left=self.config["timeout"] - i
            )
        if len(get_processes_id_by_name("msiexec")) > 1:
            raise AutomationLibraryError(
                "INSTALLATION_ERROR",
                "found too many msiexec processes, installation may be still in progress"
            )
        # 7. Add \bin to setup-folder
        self.config["setup-folder"] = os.path.join(self.config["setup-folder"],
                                                   "bin")

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
