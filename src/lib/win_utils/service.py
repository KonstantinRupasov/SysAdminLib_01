# coding: utf-8


# standard imports
import subprocess as sp


# local imports
from .win_utils import *
from ..utils.cvt import str_to_bool


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
        res = run_cmd("iisreset.exe /status", shell=True,
                      timeout=gv.CONFIG["timeout"])
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
        res = run_cmd("iisreset.exe /status", shell=True,
                      timeout=gv.CONFIG["timeout"])
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
        res = run_cmd("iisreset.exe /start", shell=True,
                      timeout=gv.CONFIG["timeout"])
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
        ), shell=True, timeout=gv.CONFIG["timeout"])
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
        res = run_cmd("wmic service \"{}\" get \"{}\"".format(service_name, key),
                      shell=True, timeout=gv.CONFIG["timeout"])
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
#
# @param params Parameters for SC. Can be str, list or tuple.
# @param timeout Time for execution.
# @return (int, CompletedProcess). int is error code (0 on success),
#  detailed explanation
#  https://msdn.microsoft.com/en-us/library/windows/desktop/ms681381(v=vs.85).aspx
def execute_sc_command(params, timeout=gv.CONFIG["timeout"]):
    # join parameters if in list or tuple
    if type(params) in [list, tuple]:
        params = " ".join(params)
    # if type of params is wrong, raise exception
    elif not (isinstance(params, str)):
        raise AutomationLibraryError("ARGS_ERROR",
                                     "params should be str, list or tuple.",
                                     actual_type=type(params))
    # execute SC command with params
    res = run_cmd("sc " + params, shell=True, timeout=timeout)
    # delete file, which can be created by SC utility
    if os.path.exists(params.split(" ")[0]):
        os.remove(params.split(" ")[0])
    return res
