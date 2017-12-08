# coding: utf-8

import sys
import os
import shlex
import re
from functools import reduce


from .linux_utils import *
from ..utils import *


CLUSTER_DEFAULT_PORT = 1540
CLUSTER_DEFAULT_REGPORT = 1541
CLUSTER_DEFAULT_RANGE = list(range(1560, 1592))
CLUSTER_DEFAULT_FOLDER = os.path.abspath(os.path.realpath(os.path.expandvars(
    os.path.expanduser(
        "~/.1cv8"
    )
)))
RAS_DEFAULT_PORT = 1545

SERVICES_DIR = ["/etc/systemd/system", ]

SCRIPT_BLANK_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(sys.argv[0]), ".."
    )
)


class SystemdService:

    systemd = "org.freedesktop.systemd1"
    systemd_object = "/org/freedesktop/systemd1"
    systemd_manager = systemd + ".Manager"
    systemd_unit = systemd + ".Unit"
    systemd_service = systemd + ".Service"

    ## Create Systemd service from blank.
    # @param path Path to blank. File name should be <name>.service.
    # @param placeholders Dict with values, which should be replaced in blank,
    #  ie {"port": 4540} will replace "<port>" string in blank. Key in dict is
    #  a <key> in blank.
    # @param service_name Service name. If omitted, service name extracts from
    #  path argument.
    @staticmethod
    def create_systemd_service_from_example(blank_path, placeholders,
                                            service_name=None):
        # if service_name not supplied, then extract it from path.
        if service_name is None:
            service_name = os.path.basename(blank_path)
        l = LogFunc(message="creating Systemd service",
                    service_name=service_name)
        # 0. Test service name and show warning, if it contains a non-standard
        # to Systemd characters.
        if service_name != systemd_escape(service_name):
            global_logger.warning(
                "Service name contain characters, which cannot be used \"as is"
                "\" by Systemd and should be escaped. This could cause troubles"
                " when managing services manually", raw_name=service_name,
                escaped_name=systemd_escape(service_name)
            )
        # 1. Read blank.
        blank_f = open(blank_path, "r")
        service_data = blank_f.read()
        # 2. Replace values in blank.
        for key, value in placeholders.items():
            service_data = service_data.replace("<{}>".format(key), str(value))
            blank_f.close()
        # 3. Delete files if exists.
        service_f_name = systemd_escape(service_name) + ".service"
        service_f_fq_name = os.path.join(
            "/etc/systemd/system/", service_f_name)
        if os.path.exists(service_f_fq_name):
            os.remove(service_f_fq_name)
        # 4. Create file in /etc/systemd/system and write it.
        service_f = open(service_f_fq_name, "w")
        service_f.write(service_data)
        service_f.close()
        # 5. Reload systemd services.
        run_cmd(["systemctl", "daemon-reload"])
        # 6. Connect to created service and return it.
        obj = SystemdService(service_name)
        obj.connect()
        return obj

    ## Test access to service control.
    # @exception AutomationLibraryError("SERVICE_ERROR")
    @staticmethod
    def test_sc_permissions():
        l = LogFunc(message="testing service control permissions")
        try:
            res = run_cmd(["systemctl", "start",
                           "AutomationLibraryTestService"], timeout=1)
        except sp.TimeoutExpired as err:
            raise AutomationLibraryError("SERVICE_ERROR", "Access error")
        if re.search("Access denied", res.stderr.decode(gv.ENCODING)) \
           is not None or \
           re.search("authentication required", res.stderr.decode(gv.ENCODING))\
           is not None:
            raise AutomationLibraryError("SERVICE_ERROR", "Access denied")

    ## Constructor.
    # @param self Pointer to object.
    # @param name Service name.
    def __init__(self, name):
        self.name = systemd_escape(name)
        self.exe_name = None
        self._connected = False
        self._unit_object = ""
        self.cmd = ""

    ## Check that service object connected to service.
    # @param self Pointer to object.
    @property
    def connected(self):
        return self._connected

    ## Connect to service.
    # @param self Pointer to object.
    # @param ignore_errors If set, then if connection fails, no exception
    #  will be raised, instead False returns.
    # @return True on success, False on fail and if ignore_errors is True.
    # @exception AutomationLibraryError("SERVICE_ERROR")
    def connect(self, ignore_errors=False):
        try:
            # get unit object
            res = run_cmd(
                "busctl call {} {} {} LoadUnit s \"{}.service\"".format(
                    SystemdService.systemd, SystemdService.systemd_object,
                    SystemdService.systemd_manager, self.name
                ), shell=True)
            if res.returncode != 0:
                raise AutomationLibraryError(
                    "SERVICE_ERROR", "Service not found",
                    busctl_stdout=res.stdout.decode(gv.ENCODING),
                    busctl_stderr=res.stderr.decode(gv.ENCODING)
                )
            self._unit_object = re.search(
                "[a-z()]+ \\\"(/[A-Za-z0-9_/]*)\\\"",
                res.stdout.decode(gv.ENCODING)
            ).groups()[0]
            # get ExecStart
            exec_start = re.findall(
                "(false|true|[0-9]+|\"(?:\\\\\\\"|[^\\\"])*\\\")",
                run_cmd("busctl get-property {} {} {} ExecStart".format(
                    SystemdService.systemd, self._unit_object,
                    SystemdService.systemd_service
                ), shell=True).stdout.decode(gv.ENCODING)
            )
            # extract executable name and full command line string
            self.exe_name = exec_start[1].strip("\"")
            self.cmd = ""
            for index in range(3, 3 + int(exec_start[2])):
                self.cmd += exec_start[index][1:-1] + " "
            self.cmd = self.cmd.strip(" ")
            self._connected = True
            return True
        except:
            if ignore_errors:
                return False
            raise AutomationLibraryError(
                "SERVICE_ERROR", "Service not found",
                service_name=self.name
            )

    ## Disconnect from service.
    # @param self Pointer to object.
    def disconnect(self):
        self._connected = False

    ## Get main process (of service) id (PID).
    # @param self Pointer to object.
    # @return PID of process.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    @property
    def process_id(self):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        return int(run_cmd("busctl get-property {} {} {} ExecMainPID".format(
            SystemdService.systemd, self._unit_object,
            SystemdService.systemd_service
        ), shell=True).stdout.decode(gv.ENCODING).split(" ")[1])

    ## Check that service started.
    # @param self Pointer to object.
    # @return True or False.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    @property
    def started(self):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        state = run_cmd("busctl get-property {} {} {} ActiveState".format(
            SystemdService.systemd, self._unit_object,
            SystemdService.systemd_unit
        ), shell=True).stdout.decode(gv.ENCODING).split(" ")[1].strip("\"\n")
        return True if state == "active" else False

    ## Start service.
    # @param self Pointer to object.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    def start(self):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        l = LogFunc(message="starting service", service_name=self.name)
        run_cmd("busctl call {} {} {} Start s replace".format(
            SystemdService.systemd, self._unit_object,
            SystemdService.systemd_unit
        ), shell=True)


    ## Stop service.
    # @param self Pointer to object.
    # @param force If True, then instead of stopping service processes will be
    #  SIGKILL'ed and dumps will be gathered.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    def stop(self, force=False):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        if force:
            self._kill()
        else:
            self._stop_service()

    ## Stop service gracefully.
    # @param self Pointer to object.
    def _stop_service(self):
        l = LogFunc(message="stopping service gracefully",
                    service_name=self.name)
        run_cmd("busctl call {} {} {} Stop s replace".format(
            SystemdService.systemd, self._unit_object,
            SystemdService.systemd_unit
        ), shell=True)

    ## Stop service hard, ie dump and kill processes.
    # @param self Pointer to object.
    def _kill(self):
        l = LogFunc(message="stopping service hard", service_name=self.name)
        # get PIDs of processes, belongs to service
        main_pid = self.process_id
        pids = get_all_child_procs(main_pid)
        pids = [main_pid, ] + pids
        global_logger.info(message="Processes, related to service", pids=pids)
        # stop all processes
        for pid in pids:
            res = run_cmd("kill -19 {}".format(pid), shell=True)
        # create dumps
        if not os.path.exists(gv.CONFIG["dumps-folder"]):
            os.makedirs(gv.CONFIG["dumps-folder"])
        for pid in pids[::-1]:
            global_logger.info(message="Creating dump for pid", dump_pid=pid,
                               dump_name="{}.dump".format(pid))
            try:
                res = run_cmd("gcore {}".format(pid),
                              shell=True, timeout=gv.CONFIG["timeout"])
                # move core file to
                run_cmd(
                    "mv core.{0} {1}/{0}.dump".format(
                        pid, gv.CONFIG["dumps-folder"]
                    ), shell=True, timeout=gv.CONFIG["timeout"]
                )
            except Exception:
                pass
        # kill processes
        for pid in pids[::-1]:
            global_logger.info(message="Killing process", value=pid)
            res = run_cmd("kill -9 {}".format(pid), shell=True)

    ## Restart service.
    # @param self Pointer to object.
    # @param force If True, then instead of stopping service processes will be
    #  SIGKILL'ed and dumps will be gathered.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    def restart(self, force=False):
        self.stop(force)
        self.start()

    ## String representation of object.
    # @param self Pointer to object.
    def __str__(self):
        return systemd_unescape(self.name)

    ## Debug representation of object.
    # @param self Pointer to object.
    def __repr__(self):
        return "SystemdService(name={},connected={})" \
            .format(systemd_unescape(self.name), self.connected)


## Alias for SystemdService class
Service = SystemdService


## Escape string via systemd-escape utility.
# @param string String to convert.
# @param encoding Encoding variable. If omitted, then encoding is get from
#  lib::common::global_vars::ENCODING.
def systemd_escape(string, encoding=None):
    if encoding is None:
        encoding = gv.ENCODING
    return run_cmd(
        "systemd-escape \"{}\"".format(string), shell=True
    ).stdout.decode(encoding).strip("\n\r")


## Revert string escape via systemd-escape utility.
# @param string String to convert.
# @param encoding Encoding variable. If omitted, then encoding is get from
#  lib::common::global_vars::ENCODING.
def systemd_unescape(string, encoding=gv.ENCODING):
    if encoding is None:
        encoding = gv.ENCODING
    return run_cmd(
        "systemd-escape -u \"{}\"".format(string), shell=True
    ).stdout.decode(encoding).strip("\n\r")


def install_service_1c(name, platform_folder, username, password,
                       cluster_folder, port=1540, regport=1541,
                       dyn_range=(1560, 1591), debug=False,
                       description=None):
    res = run_cmd(["find", "/opt/1C", "-iname", "ragent"])
    if res.returncode:
            raise AutomationLibraryError(
                "INSTALLATION_ERROR", "Cannot find Ragent executable",
            )
    platform_folder,_ = os.path.split(res.stdout.decode(gv.ENCODING).split()[0])
    # here we assume that platform_folder is standard /opt/1C/v{}.{}/<arch>
    ver_pair = re.search("/opt/1C/v(\\d).(\\d)/(?:x86_64|i386)",
                         platform_folder).groups()[0:2]
    config_name = "/etc/init.d/srv1cv{}{}" if detect_actual_os_type() \
                  == "Linux-deb" else "/etc/sysconfig/srv1cv{}{}"
    config_name = config_name.format(*ver_pair)
    dyn_range = "{}".format(dyn_range) if isinstance(dyn_range, str) else \
                "{}:{}".format(dyn_range[0], dyn_range[1])
    srv1cv8 = SystemdService.create_systemd_service_from_example(
        os.path.join(SCRIPT_BLANK_PATH, "srv1cv8.service"),
        {
            "ragent_path": platform_folder,
            "environment_file": config_name,
            "ld_path": platform_folder,
            "user": username,
            "cluster_folder": cluster_folder,
            "debug": "-debug" if debug else "",
            "port": str(port),
            "regport": str(regport),
            "range": dyn_range,
            "description": description if description is not None else ""
        },
        name
    )
    srv1cv8.connect()
    return srv1cv8


def install_ras(name, platform_folder, username, password,
                port=1545, agent_host="localhost", agent_port=1540,
                description=None):
    res = run_cmd(["find", "/opt/1C", "-iname", "ras"])
    if res.returncode:
            raise AutomationLibraryError(
                "INSTALLATION_ERROR", "Cannot find RAS executable",
            )
    platform_folder,_ = os.path.split(res.stdout.decode(gv.ENCODING).split()[0])
    ver_pair = re.search("/opt/1C/v(\\d).(\\d)/(?:x86_64|i386)",
                         platform_folder).groups()[0:2]
    config_name = "/etc/init.d/srv1cv{}{}" if detect_actual_os_type() \
                  == "Linux-deb" else "/etc/sysconfig/srv1cv{}{}"
    config_name = config_name.format(*ver_pair)
    srv1cv8_ras = SystemdService.create_systemd_service_from_example(
        os.path.join(SCRIPT_BLANK_PATH, "srv1cv8-ras.service"),
        {
            "ras_path": platform_folder,
            "ras_port": port,
            "environment_file": config_name,
            "ld_path": platform_folder,
            "user": username,
            "description": description if description is not None else "",
            "cluster_addr": "{}:{}".format(agent_host, agent_port)
        },
        name
    )
    srv1cv8_ras.connect()
    return srv1cv8_ras


def delete_service(name):
    remove_failed = False
    srvc = SystemdService(name)
    if not srvc.connect(ignore_errors=True):
        global_logger.warning(message="Service not found, so nothing to delete",
                              service=name)
        return
    for path in SERVICES_DIR:
        for file_name in os.listdir(path):
            if file_name.replace(".service", "") == name or \
               file_name.replace(".service", "") == systemd_escape(name):
                try:
                    os.remove(os.path.join(path, file_name))
                except:
                    remove_failed = True
    srvc.disconnect()
    run_cmd(["systemctl", "daemon-reload"])
    if srvc.connect(ignore_errors=True) or remove_failed:
        raise AutomationLibraryError("SERVICE_ERROR", "Cannot delete service",
                                     service=name)


def list_services():
    services_files = []
    for d in SERVICES_DIR:
        for i in os.listdir(d):
            full_path = os.path.join(d, i)
            if ".service" in i and os.path.isfile(full_path):
                services_files.append(full_path)
    pairs = []
    for i in services_files:
        service_name = re.sub("\.service$", "", os.path.basename(i))
        exec_start = re.search("^ExecStart=(.*)\\n", open(i).read(), re.M) \
                       .groups()[0]
        if exec_start is None:
            pairs.append((service_name, "", ""))
            continue
        splitted = shlex.split(exec_start)
        pairs.append((service_name, splitted[0], " ".join(splitted[1:])))
    return pairs


def find_1c_cluster_services():
    # Unlike Windows version, this function also convert arguments.
    possible_cluster_services = []
    for i in list_services():
        args = [i[1], ] + shlex.split(i[2])
        for index in range(0, len(args)):
            if "ragent" in os.path.basename(args[index]):
                possible_cluster_services.append(
                    (i[0], args[index], " ".join(args[index+1:]))
                )
    return possible_cluster_services


def find_ras_services():
    # Unlike Windows version, this function also convert arguments.
    possible_ras_services = []
    for i in list_services():
        args = [i[1], ] + shlex.split(i[2])
        for index in range(0, len(args)):
            if "ras" in os.path.basename(args[index]):
                possible_ras_services.append(
                    (i[0], args[index], " ".join(args[index+1:]))
                )
    return possible_ras_services


## Find regex in string and return first captured group.
# @param regex Regex with one group.
# @param s Input string.
# @param default This value will be returned, if found nothing found.
# @param position Index of group which should return.
# @return Founded value.
def find_in_str_or_set(regex, s, default=None, position=0):
    match = re.search(regex, s)
    if match is None:
        return default
    return match.groups()[0]


## Find key in list and return it or value, which have index
#  founded_index+offset.
# @param key What to find.
# @param List, where find.
# @param default This value will be returned, if found nothing found.
# @param offset Offset of index relative to founded key, which
#  indicate a value should be returned, ie if we perform search of "key2" in
#  list ["key1", "val1", "key2", "val2", "key3"] with offset = 1, then "val2"
#  will be returned.
def find_in_list_or_set(key, lst, default=None, offset=0):
    try:
        index = lst.index(key)
    except ValueError:
        return default
    return lst[index+offset]


## Parse service entry, which is assumed to be ragent service, and return
#  ports and cluster folder.
# @param service_entry Tuple of (name, executable, arguments).
# @return Tuple of (port, regport, rage_ports, cluster folder).
def parse_1c_cluster_service(service_entry):
    service_entry = [i.strip("\"") for i in shlex.split(service_entry[2],
                                                        posix=False)]
    port = int(find_in_list_or_set("-port", service_entry,
                                   CLUSTER_DEFAULT_PORT, 1))
    regport = int(find_in_list_or_set("-regport", service_entry,
                                      CLUSTER_DEFAULT_REGPORT, 1))
    dyn_range_str = find_in_list_or_set("-range", service_entry, "1560:1591", 1)
    dyn_range = []
    for i in dyn_range_str.split(","):
        splitted = i.split(":")
        if len(splitted) < 2:
            dyn_range.append(int(splitted[0]))
        else:
            dyn_range += range(int(splitted[0]), int(splitted[1])+1)
    dyn_range.sort()
    cluster_folder = os.path.abspath(os.path.realpath(find_in_list_or_set(
        "-d", service_entry, CLUSTER_DEFAULT_FOLDER, 1
    )))
    return port, regport, dyn_range, cluster_folder


## Parse service entry, which is assumed to be RAS, and return it port.
# @param service_entry Tuple of (name, executable, arguments).
# @return Port.
def parse_ras_service(service_entry):
    port = int(find_in_str_or_set("--port=(\d+)", service_entry[2],
                                  RAS_DEFAULT_PORT))
    return port


## Check, is specified port already used by some 1C platform service (RAS or
#  cluster).
# @param port Port.
# @@return True, if already used, False otherwise.
def is_port_used_by_1c_services(port):
    used_ports = []
    # check both cluster and ras services
    for i in find_1c_cluster_services():
        parsed = parse_1c_cluster_service(i)
        used_ports.append(parsed[0])
        used_ports.append(parsed[1])
        used_ports += parsed[2]
    for i in find_ras_services():
        parsed = parse_ras_service(i)
        used_ports.append(parsed)
    return port in used_ports


## Check, if specified folder already used by some 1C:Enterprise cluster service
#  or it it is subfolder of some service's directory or it is parent directory
#  for some service's directory.
# @param Path, which is tested.
# @return True, if already used, False otherwise.
def is_folder_used_by_1c_services(path):
    used_folders = []
    # check only cluster services
    for i in find_1c_cluster_services():
        used_folders.append(parse_1c_cluster_service(i)[3])
    path = os.path.abspath(os.path.realpath(path)) \
           + os.sep if path[-1] != os.sep else ""
    for i in used_folders:
        i = i + os.sep
        # ie one path contain another or they equal
        if i in path or path in i:
            return True
    return False


## Check, is specified name already used by some service.
# @param name Name.
# @return True, if already used, False otherwise.
def is_name_used_by_services(name):
    for i in list_services():
        if name == i[0]:
            return True
    return False


## Check, can RAS be created with specified values.
# @param name Service name.
# @param port Port.
# @return True, if service can be created, False otherwise.
def can_create_ras_service(name, port=RAS_DEFAULT_PORT):
    return not is_name_used_by_services(name) \
        and not is_port_used_by_1c_services(port)


## Check, can 1C:Enterprise cluster service be created with specified values.
# @param name Service name.
# @param port Agent port.
# @param regport Manager port.
# @param range Dynamic range.
# @param cluster_folder Cluster folder.
# @return True, if service can be created, False otherwise.
def can_create_1c_cluster_service(name, port=CLUSTER_DEFAULT_PORT,
                                  regport=CLUSTER_DEFAULT_REGPORT,
                                  dyn_range=CLUSTER_DEFAULT_RANGE,
                                  cluster_folder=CLUSTER_DEFAULT_FOLDER):
    return port != regport \
        and port not in dyn_range \
        and regport not in dyn_range \
        and not is_name_used_by_services(name) \
        and not is_port_used_by_1c_services(port) \
        and not is_port_used_by_1c_services(regport) \
        and not is_folder_used_by_1c_services(cluster_folder) \
        and not reduce(
            lambda acc, x: is_port_used_by_1c_services(x) or acc,
            dyn_range, False
        ) \
