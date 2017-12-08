# coding: utf-8

import sys

from .linux_utils import *
from .service import *
from ..utils import *
from ..utils.const import ALL, SERVER, WEB_EXTENSION, CLIENT


class Package1C:
    ## Constructor.
    # @param self Pointer to object.
    # @param os_type OS type string. Can be "Linux-deb" or "Linux-rpm".
    # @param name Middle part of name (ie without prefix).
    # @param version Package version. Can be string or
    #  lib::utils::main::PlatformVersion object.
    # @param arch Package arch (64 or 32).
    # @param prefix Prefix to name. By default:
    #  "1c-enterprise{PLATFORM_MAJOR_VERSION}{PLATFORM_MINOR_VERSION}-"
    # @param dir_path Path to package (without name).
    #  If not supplied, then package cannot be installed.
    def __init__(self, os_type, name, version, arch,
                 dir_path=None, prefix=None):
        # choose module with package manager related functions
        if os_type == "Linux-deb":
            from . import deb
            self.pm_module = deb
        elif os_type == "Linux-rpm":
            from . import rpm
            self.pm_module = rpm
        else:
            raise AutomationLibraryError("ARGS_ERROR", "wrong os_type",
                                         value=os_type)
        # setting package name
        self.pkg_name = self.pm_module.PackageName(prefix, name, version,
                                                   arch)
        # setting path to package
        if dir_path is not None:
            self.path = os.path.join(dir_path, str(self.pkg_name))
            # try_open_file(self.path)
        else:
            self.path = None

    ## DEPRECATED! Find installed version of package.
    # @param self Pointer to object.
    # @param as_platform_version Decide, should return be translated to
    #  lib::utils::main::PlatformVersion object.
    # @return String with version or None or lib::utils::main::PlatformVersion
    #  object.
    def installed_version(self, as_platform_version=False):
        result = self.pm_module.find_package_installed(
            self.pkg_name.prefix + self.pkg_name.name
        )
        return PlatformVersion(result) if as_platform_version else result

    ## String representation of object.
    # @param self Pointer to object.
    def __str__(self):
        return str(self.pkg_name)

    def __repr__(self):
        return "Package1C: pkg_name={},path={}"\
            .format(str(self.pkg_name), self.path)

    ## Install package.
    # @param simulate Simulate action or not.
    # @param force Enable forcing or not..
    # @exception AutomationLibraryError(*)
    def install(self, simulate=False, force=True):
        self.pm_module.install_package(self.path, simulate, force)

    ## Remove package.
    # @param simulate Simulate action or not.
    # @param force Enable forcing or not..
    # @exception AutomationLibraryError(*)
    def uninstall(self, simulate=False, force=True):
        self.pm_module.uninstall_package(
            self.pkg_name.prefix + self.pkg_name.name, simulate, force
        )


class Platform1CUpdater:
    ## Constructor.
    # @param self Pointer to object.
    # @param config common::config::Configuration object. If omitted, then
    #  common::global_vars::CONFIG used.
    def __init__(self, config=gv.CONFIG, uninstall_only = False, **kwargs):
        self.config = config
        # setting pm_module (deb or rpm)
        if self.config["os-type"] == "Linux-deb":
            from . import deb
            self.pm_module = deb
        elif self.config["os-type"] == "Linux-rpm":
            from . import rpm
            self.pm_module = rpm
        else:
            raise AutomationLibraryError("ARGS_ERROR", "wrong os_type",
                                         value=self.config["os-type"])
        if uninstall_only:
            return
        self.distr_path = config["download-tmp-folder"]
        try:
            self.config["new-version"] = self.config["version"]
        except:
            pass
        # setting packages
        package_dict = {
            SERVER: ["server", ],
            WEB_EXTENSION: ["ws", ],
            CLIENT: ["client", "server"],
        }
        packages_names = ["common", ]
        # if all in platform-modules, just add all from package_dict
        if ALL in self.config["platform-modules"]:
            for _, v in package_dict.items():
                packages_names += v
        # otherwise just iterate over list of platform modules and add necessary
        # names
        else:
            for module in self.config["platform-modules"]:
                packages_names += package_dict[module]
        # make sure that all packages will appear only once
        packages_names = list(set(packages_names))
        # check new version
        if len(config["new-version"].version) < 3:
            raise AutomationLibraryError("ARGS_ERROR", "incorrect new-version",
                                         current_version=config["new-version"])
        self.packages = [
            Package1C(
                config["os-type"], package_name, config["new-version"],
                config["arch"], self.distr_path
            ) for package_name in packages_names
        ]
        # if found language, which is not EN or RU, add -nls packages
        # to installation
        if "languages" in self.config:
            langs = self.config["languages"].upper().split(",")
            for l in langs:
                if l.strip(" ,") not in ["RU", "EN"]:
                    temp_packages = []
                    for package in packages_names:
                        temp_packages.append(Package1C(
                            config["os-type"],
                            package + "-nls", config["new-version"],
                            config["arch"], self.distr_path
                        ))
                    self.packages += temp_packages
                    break
        global_logger.info("Packages to update", value=self.packages)


    ## Testing service control permissions.
    # @param self Pointer to object.
    def test_sc_permissions(self):
        SystemdService.test_sc_permissions()

    ## Testing installation permissions.
    # @param self Pointer to object.
    def test_install_permissions(self):
        l = LogFunc(message="testing permissions")
        self.pm_module.test_permissions()

    ## Install services.
    # @param self Pointer to object.
    def install_services(self):
        l = LogFunc(message="Install services")
        # building platform install folder
        platform_folder = "/opt/1C/v{}.{}/{}".format(
            self.config["new-version"][0], self.config["new-version"][1],
            "x86_64" if self.config["arch"] == 64 else "i386"
        )
        install_service_1c(
            self.config["service-1c"]["name"], platform_folder,
            self.config["service-1c"]["login"],
            self.config["service-1c"]["password"],
            self.config["cluster-folder"],
        )
        install_ras(
        self.config["ras"]["name"], platform_folder,
            self.config["ras"]["login"],
            self.config["ras"]["password"]
        )

    ## Test update (ie is packages is correct, can be installed etc).
    # @param self Pointer to object.
    def test_update(self):
        l = LogFunc(message="Testing update")
        for package in self.packages:
            package.install(True, True)

    def test_old_version(self):
        # get list of installed platform packages
        packages = self.pm_module.get_installed_platform_packages()
        # generate list of installed package versions
        versions = list(set([pkg["version"] for pkg in packages]))
        # if old-version not empty and not in versions, raise an error
        if self.config["old-version"] != "" and \
           self.config["old-version"].str_linux() not in versions:
            # if versions contain only one value, print it one way,
            # if many - different
            if len(versions) == 1:
                raise AutomationLibraryError(
                    "OLD_VERSION_DOESNT_MATCH",
                    str(PlatformVersion(versions[0])),
                    self.config["old-version"]
                )
            else:
                raise AutomationLibraryError(
                    "OLD_VERSION_DOESNT_MATCH",
                    [str(PlatformVersion(version)) for version in versions],
                    self.config["old-version"]
                )
        if len(packages) < 1:
            if self.config["old-version"] != "":
                raise AutomationLibraryError(
                    "INSTALL_ERROR",
                    "Can't uninstall old version, because nothing to uninstall",
                    old_version=self.config["old-version"]
                )
            else:
                global_logger.info(message="Nothing to uninstall")
                raise AutomationLibraryError("OK")
    ## Uninstall old version of platform.
    # @param self Pointer to object.
    def uninstall_old(self):
        l = LogFunc(message="Uninstall old version of platform")
        # get list of installed platform packages
        packages = self.pm_module.get_installed_platform_packages()
        # test_old_versions
        try:
            self.test_old_version()
        except AutomationLibraryError as err:
            # if returned OK code, it means that no packages found
            if err.num_code == AutomationLibraryError("OK").num_code:
                print("OK")
                return
            else:
                raise
        # uninstall packages
        self.pm_module.uninstall_packages(packages)

    ## Update platform.
    # @param self Pointer to object.
    def update(self):
        l = LogFunc(message="Update 1C:Enterprise Platform")
        # 0. Remove old installation of platform.
        self.uninstall_old()
        # 0.1. Creating cluster folder.
        if not os.path.exists(self.config["cluster-folder"]):
            os.makedirs(self.config["cluster-folder"], exist_ok=True)
        run_cmd(["chown", "-R",
                 "{}".format(self.config["service-1c"]["login"]),
                 self.config["cluster-folder"]])
        # 1. Install new version.
        install_log = LogFunc(message="Install platform")
        for package in self.packages:
            package.install(False, True)
        del install_log
        # 2. Install services.
        if not set(self.config["platform-modules"])\
           .isdisjoint(set([SERVER, ALL])):
            self.install_services()
            # disable srv1cv83
            run_cmd(["update-rc.d", "srv1cv{}{}".format(
                self.config["new-version"].version[0],
                self.config["new-version"].version[1]
            ), "disable"])
        self.clean_temps()
        # 3. Copy web-extension.
        if not set(self.config["platform-modules"])\
           .isdisjoint(set([ALL, WEB_EXTENSION])):
            copy_web_library(self.config["web-library"]["path"],
                             self.config["setup-folder"])

    def update2(self):
        l = LogFunc(message="Install platform")
        for package in self.packages:
            package.install(False, True)

    def copy_web_library2(self):
        dll_table = {
            "apache2.0": "wsapch2.so",
            "apache2.2": "wsap22.so",
            "apache2.4": "wsap24.so",
        }
        head, tail = os.path.split(self.config["web-extension/path"])
        if not os.path.exists(head):
            os.makedirs(head)
        res = run_cmd(["find", "/opt/1C", "-iname",
                       dll_table[self.config["web-extension/web-server"]]])
        if res.returncode:
            raise AutomationLibraryError(
                "INSTALLATION_ERROR", "Cannot find web extension library",
                library_name=dll_table[
                    self.config["web-extension/web-server"]
                ]
            )
        src = res.stdout.decode(gv.ENCODING).split()[0]
        try:
            shutil.copy2(src, self.config["web-extension/path"])
        except shutil.SameFileError:
            pass


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
