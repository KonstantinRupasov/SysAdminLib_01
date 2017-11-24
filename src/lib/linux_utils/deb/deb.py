# coding: utf-8

import re
import subprocess as sp

from ...common import global_vars as gv
from ...common.errors import AutomationLibraryError
from ...common.logger import global_logger, LogFunc
from ...utils import PlatformVersion, try_open_file
from ...utils.cmd import run_cmd

ARCHIVE64_DISTR_NAME = "deb64.tar.gz"
ARCHIVE32_DISTR_NAME = "deb.tar.gz"


## Class, which describe name and version of deb-package.
class PackageName:
    ## Constructor.
    # @param self Pointer to object
    # @param name Middle part of name.
    # @param version Package version. Can be string or
    #  lib::utils::main::PlatformVersion object.
    # @param bitness Package bitness (64 or 32).
    # @param prefix Prefix to name. By default:
    #  "1c-enterprise{PLATFORM_MAJOR_VERSION}{PLATFORM_MINOR_VERSION}-"
    def __init__(self, prefix, name, version, bitness):
        self.name = name
        self.version = version if isinstance(version, PlatformVersion) else \
            PlatformVersion(version)
        self.prefix = "1c-enterprise{}{}-".format(*self.version.version[0:2]) \
                      if prefix is None else prefix
        self.bitness = "amd64" if bitness == 64 else "i386"

    ## String representation of object.
    # @param self Pointer to object.
    def __str__(self):
        return "{}{}_{}_{}.deb".format(self.prefix, self.name,
                                       self.version.str_linux(),
                                       self.bitness)

    ## Debug representation of object.
    # @param self Pointer to object.
    def __repr__(self):
        return "PackageName: " + str(self)


## Install package.
# @param path Full path to package.
# @param simulate Simulate action or not.
# @param force Enable forcing or not..
# @exception AutomationLibraryError(*)
def install_package(path, simulate=False, force=True):
    # set force params
    forces = "--force-all" if force \
             else ""
    # set simulate params
    simulate_str = "--simulate" if simulate else ""
    # run install command
    try:
        res = run_cmd("dpkg -i {} {} {}".format(forces, simulate_str,
                                                path),
                      timeout=gv.CONFIG["timeout"], shell=True)
        global_logger.debug("package installation",
                            returncode=res.returncode,
                            stdout=res.stdout.decode(gv.ENCODING),
                            stderr=res.stderr.decode(gv.ENCODING)
        )
    except sp.TimeoutExpired as err:
        raise AutomationLibraryError("TIMEOUT_ERROR")
    else:
        if res.returncode != 0:
            raise AutomationLibraryError("DPKG_ERROR",
                                         reason=res.stderr.decode(gv.ENCODING))


## Remove package.
# @param name Name of the package.
# @param simulate Simulate action or not.
# @param force Enable forcing or not.
# @exception AutomationLibraryError(*)
def uninstall_package(name, simulate=False, force=True):
    forces = "--force-all" if force \
             else ""
    simulate_str = "--simulate" if simulate else ""
    try:
        res = run_cmd("dpkg -r {} {} {}".format(forces, simulate_str,
                                                name),
                      timeout=gv.CONFIG["timeout"], shell=True)
    except sp.TimeoutExpired as err:
        raise AutomationLibraryError("TIMEOUT_ERROR")
    else:
        if res.returncode != 0:
            raise AutomationLibraryError("DPKG_ERROR",
                                         reason=res.stderr.decode(gv.ENCODING))


## Testing permissions dpkg
def test_dpkg_perm():
    res = run_cmd(["dpkg", "-i", "test.deb", "--simulate"])
    if res.returncode == 2:
        if re.search(r"superuser", res.stderr.decode(gv.ENCODING)):
            return False
        else:
            return True
    if res.returncode == 0:
        return True


## Testing permissions.
# @param update_data Ignore.
# @exception AutomationLibraryError(*)
def test_permissions():
    l = LogFunc(message="permission test")
    # checking permissions of dpkg
    if test_dpkg_perm() is False:
        raise AutomationLibraryError("DPKG_PERM_DENIED")
    # testing access to /etc/systemd/system
    try_open_file("/etc/systemd/system/srv1cv8", "a", False)
    # testing access to /tmp folder
    try_open_file("/tmp/test.deb", "a", False)


## Find installed version of package.
# @param name Name (or its part) of package/
# @return String with version or None.
def find_package_installed(name):
    # getting package status
    res = run_cmd(["dpkg", "--status", name])
    if res.returncode != 0:
        return None
    # extracting full package name from this data
    search_package_result = re.search("^Package.*?([^: ]*)$",
                                      res.stdout.decode(gv.ENCODING),
                                      re.MULTILINE)
    if name != search_package_result.groups()[0]:
        return None
    # sure that package installed
    search_installed_result = re.search("installed",
                                        res.stdout.decode(gv.ENCODING),
                                        re.MULTILINE)
    # extracting package version
    if search_package_result is not None \
            and search_installed_result is not None:
        search_version_result = re.search("^Version.*?([^: ]*)$",
                                          res.stdout.decode(gv.ENCODING),
                                          re.MULTILINE)
        return search_version_result.groups()[0]
    else:
        return None


## Getting installed platform version.
# @param config dict or dict-like object with "old-version" and "bitness" values.
# @return lib::utils::main::PlatformVersion object.
def get_installed_platform_version(config):
    package_name = PackageName(
        None, "common", config["old-version"],
        config["bitness"]
    )
    package_name = package_name.prefix + package_name.name
    return PlatformVersion(find_package_installed(package_name))


## Return list of installed 1C:Enterprise Platform packages.
# @return List of dicts.
def get_installed_platform_packages():
    # query all installed 1c-enterprise* packages
    res = run_cmd(
        "dpkg-query -W -f='${binary:Package}\\t${Architecture}\\t${Version}\\t\\n' "
        "'1c-enterprise*' | grep -e 'enterprise[0-9]\\{1,\\}'", shell=True,
        timeout=gv.CONFIG["timeout"]
    )
    # if query returned nothing, return empty list
    if res.returncode != 0:
        return list()
    packages = list()
    # parse each line and fill dict
    for package_str in res.stdout.decode(gv.ENCODING).split("\n")[:-1]:
        parts = package_str.split("\t")
        package = { "name": parts[0].split("-")[-1], "fullname": parts[0],
                    "version": parts[2], "arch": parts[1] }
        packages.append(package)
    return packages


## Uninstall packages.
# @param packages List of dicts, returned by get_installed_platform_packages().
# @param simulate Simulate action or not.
# @param force Enable forcing or not.
# @exception AutomationLibraryError("TIMEOUT_ERROR") If time expired.
# @exception AutomationLibraryError("DPKG_ERROR") If error occurred during
#  uninstall.
def uninstall_packages(packages, simulate=False, force=True):
    packages_str = " ".join([pkg["fullname"] for pkg in packages])
    forces = "--force-all" if force \
             else ""
    simulate_str = "--simulate" if simulate else ""
    try:
        res = run_cmd("dpkg -P {} {} {}".format(forces, simulate_str,
                                                packages_str),
                      timeout=gv.CONFIG["timeout"], shell=True)
    except sp.TimeoutExpired as err:
        raise AutomationLibraryError("TIMEOUT_ERROR")
    else:
        if res.returncode != 0:
            raise AutomationLibraryError(
                "DPKG_ERROR", reason=res.stderr.decode(gv.ENCODING)
            )
