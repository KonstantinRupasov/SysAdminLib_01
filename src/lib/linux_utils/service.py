# coding: utf-8


from .linux_utils import *


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
