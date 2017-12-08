# coding: utf-8


# standard imports
import subprocess as sp
import sys
import os
import shlex
import re
import platform
from functools import reduce


# local imports
from .win_utils import *
from ..utils.cvt import str_to_bool


CLUSTER_DEFAULT_PORT = 1540
CLUSTER_DEFAULT_REGPORT = 1541
CLUSTER_DEFAULT_RANGE = list(range(1560, 1592))
CLUSTER_DEFAULT_FOLDER = os.path.abspath(os.path.realpath(os.path.expandvars(
    os.path.expanduser(
        "%USERPROFILE%\\Local Settings\\Application Data\\1C\\1cv8" if \
        int(platform.win32_ver()[1][0]) < 6 else "%LOCALAPPDATA%\\1C\\1cv8"
    )
)))
RAS_DEFAULT_PORT = 1545


## Represent Windows service.
class Service:

    ## Test access to service control.
    # @param obj User name. Can be omitted.
    # @param password User password. Can be omitted.
    @staticmethod
    def test_sc_permissions(obj=None, password=None):
        l = LogFunc(message="testing service control permissions",
                    obj=obj, password=password)
        # build sc command
        cmd = "create \"AutomationLibraryTestService\" binpath= \"\\dev\\null\""
        # add user data to sc command, if necessary
        if type(obj) is str and obj != "":
            cmd += " obj= \"{}\"".format(obj)
            if password != "" and password is not None:
                cmd += " password= \"{}\"".format(password)
        # delete service just to be sure
        execute_sc_command("delete \"AutomationLibraryTestService\"")
        # create and run service, delete anyway
        res = execute_sc_command(cmd)
        # 0 - success, 2 - file not found
        if res.returncode not in [0, 2]:
            execute_sc_command("delete \"AutomationLibraryTestService\"")
            raise AutomationLibraryError("SERVICE_ERROR",
                                         format_message(res.returncode),
                                         sc_code=res.returncode,
                                         obj=obj, password=password)
        res = execute_sc_command("start \"AutomationLibraryTestService\"")
        # 0 - success, 2 - file not found
        if res.returncode not in [0, 2]:
            execute_sc_command("delete \"AutomationLibraryTestService\"")
            raise AutomationLibraryError("SERVICE_ERROR",
                                         format_message(res.returncode),
                                         sc_code=res.returncode,
                                         obj=obj, password=password)
        execute_sc_command("delete \"AutomationLibraryTestService\"")

    ## Constructor.
    # @param self Pointer to object.
    # @param name Service name.
    def __init__(self, name):
        self.name = name
        self.exe_name = None
        self._connected = False
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
        # testing service existence
        try:
            get_service_property(self.name, "Name")
        # if ignore_errors is True, then return False, else reraise occurred
        # exception
        except Exception:
            if ignore_errors:
                return False
            else:
                raise AutomationLibraryError(
                    "SERVICE_ERROR", "not found", name=self.name
                )
        # extract command and executable path of service
        self.cmd = get_service_property(self.name, "PathName")
        try:
            self.exe_name = re.search(r"\"?(.*\.exe).*", self.cmd) \
                              .groups()[0]
        except Exception:
            self.exe_name = re.search(r"\"?([^ ]*).*", self.cmd) \
                              .groups()[0]
        self._connected = True
        return True

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
        return int(get_service_property(self.name, "ProcessId"))

    ## Check that service started.
    # @param self Pointer to object.
    # @return True or False.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    @property
    def started(self):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        return str_to_bool(get_service_property(self.name, "started"))

    ## Start service.
    # @param self Pointer to object.
    # @exception AutomationLibraryError("SERVICE_ERROR")
    def start(self):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        l = LogFunc(message="starting service", service_name=self.name)
        res = execute_sc_command("start \"{}\"".format(self.name))
        if res.returncode not in [0, 1056]:
            raise AutomationLibraryError("SERVICE_ERROR", "can't start service",
                                         service_name=self.name,
                                         returncode=res.returncode)

    ## Stop service.
    # @param self Pointer to object.
    # @param force If True, then instead of stopping service processes will be
    #  terminate()'ed and dumps will be gathered.
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
        res = execute_sc_command("stop \"{}\"".format(self.name))
        if res.returncode not in [0, 1062]:
            raise AutomationLibraryError("SERVICE_ERROR", "can't stop service",
                                         service_name=self.name,
                                         returncode=res.returncode)

    ## Stop service brutally, ie dump and kill processes.
    # @param self Pointer to object.
    def _kill(self):
        l = LogFunc(message="stopping service hard",
                    service_name=self.name)
        # get list of processes
        main_pid = self.process_id
        res = run_cmd(
            "wmic process where (ParentProcessID={}) get ProcessID".format(
                main_pid
            ), shell=True
        )
        temp_list = [i.strip("\n\r ") for i in res.stdout.decode(gv.ENCODING)
                     .split("\n")]
        pids = list()
        for entry in temp_list:
            try:
                pids.append(int(entry))
            except Exception:
                pass
        # add main_pid to pids list
        pids = [main_pid, ] + pids
        # create dumps
        for pid in pids[::-1]:
            make_dump(pid, 0x2, gv.CONFIG["dumps-folder"])
        # kill processes
        for pid in pids[::-1]:
            kill_process(pid)

    ## Restart service.
    # @param self Pointer to object.
    # @param force If True, then instead of stopping service processes will be
    #  terminate()'ed and dumps will be gathered.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    def restart(self, force=False):
        self.stop(force)
        self.start()

    ## Create service.
    # @param self Pointer to object.
    # @param cmd Command, that should be executed.
    # @param user User name. If user name doesn't contain domain part, ".\" will
    #  be added automatically.
    # @param pwd User password.
    # @param type Type (for details see "sc /?").
    # @param start Start (for details see "sc /?").
    # @param display_name If omitted, self.name will be used.
    def create(self, cmd, user, pwd, _type="own", start="demand",
               display_name=None):
        l = LogFunc(message="creating service", service_name=self.name)
        # add domain part, if not contain
        if "\\" not in user:
            user = ".\\" + user
        # set display_name if necessary
        if display_name is None:
            display_name = self.name
        # execute service creation
        res = execute_sc_command(
            "create \"{}\" binpath= \"{}\" type= {} start= {} "
            "obj= \"{}\" displayname= \"{}\" password= \"{}\"".format(
                self.name, cmd, _type, start, user, display_name, pwd
            )
        )
        # 0 - success, 1073 - already
        if res.returncode not in [0, 1073]:
            raise AutomationLibraryError("SERVICE_ERROR",
                                         "service creation failed",
                                         returncode=res.returncode,
                                         stdout=res.stdout.decode(gv.ENCODING),
                                         stderr=res.stderr.decode(gv.ENCODING))
        self.connect()

    ## Delete service.
    # @param self Pointer to object.
    def delete(self):
        l = LogFunc(message="removing service", service_name=self.name)
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        if self.started:
            self.stop()
        #run_cmd("wmic service \"{}\" call delete".format(self.name))
        res = execute_sc_command("delete \"{}\"".format(self.name))
        if res.returncode not in [0, 1060]:
            raise AutomationLibraryError("SERVICE_ERROR", "can't delete service",
                                         service_name=self.name,
                                         returncode=res.returncode,
                                         stdout=res.stdout.decode(gv.ENCODING),
                                         stderr=res.stderr.decode(gv.ENCODING))
        self._connected = False

    def set_description(self, description):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        res = execute_sc_command("description {} \"{}\"".format(self.name,
                                                                description))

    def __str__(self):
        return self.name

    def __repr__(self):
        return "Service(name={},connected={})" \
            .format(self.name, self.connected)


## Represent Windows IIS service.
class IISService:

    ## Test access to IIS utility iisreset.exe.
    @staticmethod
    def test_sc_permissions():
        res = run_cmd("iisreset.exe /status", shell=True)
        if res.returncode == 5:
            raise AutomationLibraryError("SERVICE_ERROR",
                                         "IIS permission denied")

    ## Constructor.
    # @param self Pointer to object.
    def __init__(self, *args, **kwargs):
        self._connected = False
        self.name = "IIS"
        self.services = list()

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
        # trying to invoke iisreset.exe. If successful, then assume that IIS
        # installed and we have access to it
        res = run_cmd("iisreset.exe /status", shell=True)
        if res == 9009:
            if ignore_errors:
                return False
            else:
                raise AutomationLibraryError(
                    "SERVICE_ERROR",
                    "can't invoke iisreset.exe. Probably IIS not "
                    "installed or iisreset.exe not in PATH variable."
                )
        if res.returncode != 0:
            global_logger.warning(message="Invoke of iisreset.exe successful, "
                                  "but return code not 0 ({}), which mean "
                                  "something goes wrong".format(res.returncode))
        # get IIS services
        for srvc in res.stdout.decode(gv.ENCODING).split("\n"):
            match = re.search("\\( (.*) \\)", srvc)
            if match is None:
                continue
            self.services.append(Service(match.groups()[0]))
            self.services[-1].connect()
        global_logger.debug(message="IIS services", services=self.services)
        self._connected = True
        return True

    ## Check that service started.
    # @param self Pointer to object.
    # @return True or False.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    @property
    def started(self):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        started = True
        # check, that each IIS service has been started
        for service in self.services:
            started = service.started and started
        return started

    ## Start service.
    # @param self Pointer to object.
    # @exception AutomationLibraryError("SERVICE_ERROR")
    def start(self):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        l = LogFunc(message="starting service", service_name=self.name)
        res = run_cmd("iisreset.exe /start", shell=True)
        if res.returncode not in [0, 1056]:
            raise AutomationLibraryError("SERVICE_ERROR", "can't start service",
                                         service_name=self.name,
                                         returncode=res.returncode)
        self._started = True

    ## Stop service.
    # @param self Pointer to object.
    # @param force If True, then instead of stopping service processes will be
    #  terminate()'ed.
    def stop(self, force=False):
        if not self.connected:
            raise AutomationLibraryError("SERVICE_ERROR", "Not connected")
        l = LogFunc(message="stopping service {}".format(
            "gracefully" if not force else "hard"
        ), service_name=self.name)
        res = run_cmd("iisreset.exe /stop {}".format(
            "" if force else "/noforce"
        ), shell=True)
        if res.returncode not in [0, 1062]:
            raise AutomationLibraryError("SERVICE_ERROR", "can't stop service",
                                         service_name=self.name,
                                         returncode=res.returncode)

    ## Restart service.
    # @param self Pointer to object.
    # @param force If True, then instead of stopping service processes will be
    #  terminate()'ed.
    # @exception AutomationLibraryError("SERVICE_ERROR") If not connected.
    def restart(self, force=False):
        self.stop(force)
        self.start()

    def __str__(self):
        return self.name

    def __repr__(self):
        return "Service(name={},connected={})" \
            .format(self.name, self.connected)


## Get service property.
# @param service_name Service name.
# @param key Property name.
# @return String with value.
# @exception AutomationLibraryError("SERVICE_NOT_FOUND") If service not found.
# @exception AutomationLibraryError("SERVICE_PROPERTY_NOT_FOUND") Property not found.
# @exception AutomationLibraryError("TIMEOUT_ERROR")
def get_service_property(service_name, key):
    # make wmic request
    try:
        res = run_cmd("wmic service \"{}\" get {}".format(service_name, key),
                      shell=True)
    except sp.TimeoutExpired:
        raise AutomationLibraryError("TIMEOUT_ERROR")
    # if stderr not empty, then service not found
    if len(res.stderr) > 0:
        raise AutomationLibraryError("SERVICE_ERROR", "service not found",
                                     service=service_name)
    # if returncode not 0, then property not found
    if res.returncode != 0:
        raise AutomationLibraryError("SERVICE_ERROR", "property not found",
                                     property=key)
    return res.stdout.decode(gv.ENCODING).split("\n")[1].strip("\n\r ")


## Execute SC command with parameters.
# @param params Parameters for SC. Can be str, list or tuple.
# @param timeout Time for execution.
# @return (int, CompletedProcess). int is error code (0 on success),
#  detailed explanation
#  https://msdn.microsoft.com/en-us/library/windows/desktop/ms681381(v=vs.85).aspx
def execute_sc_command(params):
    # join parameters if in list or tuple
    if type(params) in [list, tuple]:
        params = " ".join(params)
    # if type of params is wrong, raise exception
    elif not (isinstance(params, str)):
        raise AutomationLibraryError("ARGS_ERROR",
                                     "params should be str, list or tuple.",
                                     actual_type=type(params))
    # execute SC command with params
    res = run_cmd("sc " + params, shell=True)
    # delete file, which can be created by SC utility
    if os.path.exists(params.split(" ")[0]):
        os.remove(params.split(" ")[0])
    return res


## Install 1C:Enterprise cluster (ragent) service.
def install_service_1c(name, platform_folder, username, password,
                       cluster_folder, port=1540, regport=1541,
                       dyn_range=(1560, 1591), debug=False, description=None):
    srv1cv8 = Service(name)
    # TODO: decide, should existing service be deleted or error should be raised
    if srv1cv8.connect(True):
        srv1cv8.delete()
        srv1cv8.disconnect()
    ragent_name = "ragent.exe"
    if not os.path.exists(os.path.join(platform_folder, ragent_name)):
        old_platform_folder = platform_folder
        platform_folder = os.path.join(platform_folder, "bin")
        if not os.path.exists(os.path.join(platform_folder, ragent_name)):
            raise AutomationLibraryError(
                "ARGS_ERROR", "ragent.exe not found in specified folder",
                folder=old_platform_folder
            )
    dyn_range = "{}".format(dyn_range) if isinstance(dyn_range, str) else \
                "{}:{}".format(dyn_range[0], dyn_range[1])
    # building command
    cmd = "\"{}\" -srvc -agent -port {} -regport {} -range {}" \
          " -d {} {}".format(
              os.path.join(platform_folder, ragent_name),
              port, regport, dyn_range,
              cluster_folder, "-debug" if debug else ""
          )
    srv1cv8.create(
        cmd,
        username,
        password
    )
    srv1cv8.connect()
    if description is not None:
        srv1cv8.set_description(description)
    return srv1cv8


## Install RAS service.
def install_ras(name, platform_folder, username, password,
                port=1545, agent_host="localhost", agent_port=1540,
                description=None):
    srv1cv8_ras = Service(name)
    # TODO: decide, should existing service be deleted or error should be raised
    if srv1cv8_ras.connect(True):
        srv1cv8_ras.delete()
        srv1cv8_ras.disconnect()
    ras_name = "ras.exe"
    if not os.path.exists(os.path.join(platform_folder, ras_name)):
        old_platform_folder = platform_folder
        platform_folder = os.path.join(platform_folder, "bin")
        if not os.path.exists(os.path.join(platform_folder, ras_name)):
            raise AutomationLibraryError(
                "ARGS_ERROR", "ras.exe not found in specified folder",
                folder=old_platform_folder
            )
    srv1cv8_ras.create(
        "\"{}\" cluster --service --port={} {}:{}".format(
            os.path.join(platform_folder, ras_name),
            port, agent_host, agent_port
        ),
        username,
        password
    )
    srv1cv8_ras.connect()
    if description is not None:
        srv1cv8_ras.set_description(description)
    return srv1cv8_ras


## Delete service. Raise exception, if service not found.
# @param name Name of service.
def delete_service(name):
    srvc = Service(name)
    if not srvc.connect(ignore_errors=True):
        global_logger.warning(message="Service not found, so nothing to delete",
                              service=name)
        return
    srvc.delete()
    srvc.disconnect()
    if srvc.connect(ignore_errors=True):
        raise AutomationLibraryError("SERVICE_ERROR", "Cannot delete service",
                                     service=name)


## List all services in OS.
# @return List of tuples (name, executable, arguments)
def list_services():
    res = run_cmd("wmic service get Name,PathName")
    result_strings =  [i for i in res.stdout.decode(gv.ENCODING) \
                       .replace("\r", "").split("\n") if i != ""]
    cmd_start_position = result_strings[0].find("PathName")
    pairs = []
    for i in result_strings:
        splitted = shlex.split(i[cmd_start_position:], posix=False)
        pairs.append((i[0:cmd_start_position].strip(" "),
                      splitted[0].strip(" \""),
                      " ".join(splitted[1:])))
    return pairs


## Find all services in OS, which run ragent.
# @return List of tuples (name, executable, arguments)
def find_1c_cluster_services():
    return [i for i in list_services() if "ragent" in \
            os.path.basename(os.path.realpath(i[1]))]


## Find all services in OS, which run ras.
# @return List of tuples (name, executable, arguments)
def find_ras_services():
    return [i for i in list_services() if "ras" in \
            os.path.basename(os.path.realpath(i[1]))]


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
    path = os.path.abspath(os.path.realpath(path)) + os.sep
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
