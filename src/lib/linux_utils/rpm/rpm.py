# coding: utf-8

import re
import subprocess as sp

from ...common import global_vars as gv
from ...common.errors import AutomationLibraryError
from ...common.logger import global_logger, LogFunc
from ...utils import PlatformVersion, try_open_file
from ...utils.cmd import run_cmd

ARCHIVE64_DISTR_NAME = "rpm64.tar.gz"
ARCHIVE32_DISTR_NAME = "rpm.tar.gz"


## Class, which describe name and version of deb-package.
class PackageName:
    ## Constructor.
    # @param self Pointer to object
    # @param name Middle part of name.
    # @param version Package version. Can be string or
    #  lib::utils::main::PlatformVersion object.
    # @param arch Package arch (64 or 32).
    # @param prefix Prefix to name. By default:
    #  "1C_Enterprise{PLATFORM_MAJOR_VERSION}{PLATFORM_MINOR_VERSION}-"
    def __init__(self, prefix, name, version, arch):
        self.name = name
        self.version = version if isinstance(version, PlatformVersion) else \
            PlatformVersion(version)
        self.prefix = "1C_Enterprise{}{}-".format(*self.version.version[0:2]) \
                      if prefix is None else prefix
        self.arch = "x86_64" if arch == 64 else "i386"

    ## String representation of object.
    # @param self Pointer to object.
    def __str__(self):
        return "{}{}-{}.{}.rpm".format(self.prefix, self.name,
                                       self.version.str_linux(),
                                       self.arch)

    ## Debug representation of object.
    # @param self Pointer to object.
    def __repr__(self):
        return "PackageVersion: " + str(self)


## Install package.
# @param path Full path to package.
# @param simulate Simulate install or not.
# @param force Enable forcing or not..
# @exception AutomationLibraryError(*)
def install_package(path, simulate=False, force=True):
    forces = "--force" if force \
             else ""
    simulate_str = "--test" if simulate else ""
    try:
        res = run_cmd("rpm -Uvh --nodeps {} {} {}".format(forces, simulate_str,
                                                          path),
                      shell=True)
        global_logger.info("package installation",
                           returncode=res.returncode,
                           stdout=res.stdout.decode(gv.ENCODING),
                           stderr=res.stderr.decode(gv.ENCODING)
                           )
    except sp.TimeoutExpired as err:
        raise AutomationLibraryError("TIMEOUT_ERROR")
    else:
        if res.returncode != 0:
            raise AutomationLibraryError("RPM_ERROR",
                                         reason=res.stderr.decode(gv.ENCODING))


## Remove package.
# @param name Name of the package.
# @param simulate Simulate action or not.
# @param force Enable forcing or not..
# @exception AutomationLibraryError(*)
def uninstall_package(name, simulate=False, force=True):
    forces = "--force" if force \
             else ""
    simulate_str = "--test" if simulate else ""
    try:
        res = run_cmd("rpm -evh --nodeps {} {} {}".format(forces, simulate_str,
                                                          name),
                      shell=True)
    except sp.TimeoutExpired as err:
        raise AutomationLibraryError("TIMEOUT_ERROR")
    else:
        if res.returncode != 0:
            raise AutomationLibraryError("RPM_ERROR",
                                         reason=res.stderr.decode(gv.ENCODING))


def uninstall_packages(packages, simulate=False, force=True):
    packages_str = " ".join(
        ["".join([pkg.pkg_name.prefix, pkg.pkg_name.name]) \
         for pkg in packages]
    )
    print(packages)
    forces = "--force" if force \
             else ""
    simulate_str = "--test" if simulate else ""
    try:
        res = run_cmd("rpm --evh --nodeps {} {} {}".format(forces, simulate_str,
                                                           packages_str),
                      shell=True)
    except sp.TimeoutExpired as err:
        raise AutomationLibraryError("TIMEOUT_ERROR")
    else:
        if res.returncode != 0:
            raise AutomationLibraryError(
                "RPM_ERROR", reason=res.stderr.decode(gv.ENCODING)
            )


## Testing permissions to rpm
def test_rpm_perm():
    res = run_cmd(["echo "" >> /var/lib/rpm/.rpm.lock"], shell=True)
    if res.returncode == 1:
        if re.search(r"denied", res.stderr.decode(gv.ENCODING)):
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
    if test_rpm_perm() is False:
        raise AutomationLibraryError("RPM_PERM_DENIED")

    # testing access to /etc/systemd/system
    try_open_file("/etc/systemd/system/srv1cv8", "a", False)

    # testing access to /tmp folder
    try_open_file("/tmp/test.rpm", "a", False)


## Find installed version of package
# @param name Name (or its part) of package
# @return String with version or None.
def find_package_installed(name):
    res = run_cmd("rpm -qa | grep -i {}".format(name), shell=True)
    if res.returncode != 0 and res.stdout != b"":
        return None
    full_name = res.stdout.decode(gv.ENCODING)
    return re.search(".*-(\\d+\\.\\d+\\.\\d+-\\d+)\\..*",
                     full_name).groups()[0]


## Getting installed platform version.
# @param config dict or dict-like object with "old-version" and "arch" values.
# @return lib::utils::main::PlatformVersion object.
def get_installed_platform_version(config):
    package_name = PackageName(
        None, "common", config["old-version"],
        config["arch"]
    )
    package_name = package_name.prefix + package_name.name
    return PlatformVersion(find_package_installed(package_name))


## Return list of installed 1C:Enterprise Platform packages.
# @return List of dicts.
def get_installed_platform_packages():
    # query all installed 1c-enterprise* packages
    res = run_cmd(
        "rpm -qa --queryformat \"%{n}\\t%{arch}\\t%{v}-%{release}\\t\\n\" "
        "'1C_Enterprise*' | grep -e 'Enterprise[0-9]\\{1,\\}'", shell=True,
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
def uninstall_packages(packages, simulate=False):
    packages_str = " ".join([pkg["fullname"] for pkg in packages])
    simulate_str = "--test" if simulate else ""
    try:
        res = run_cmd("rpm -evh --nodeps {} {}".format(simulate_str,
                                                          packages_str),
                      shell=True)
    except sp.TimeoutExpired as err:
        raise AutomationLibraryError("TIMEOUT_ERROR")
    else:
        if res.returncode != 0:
            raise AutomationLibraryError(
                "RPM_ERROR", reason=res.stderr.decode(gv.ENCODING)
            )
