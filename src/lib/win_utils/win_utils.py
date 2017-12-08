# coding: utf-8

import shutil
from ctypes import *
from ctypes.wintypes import *

from ..utils import *

ARCHIVE64_DISTR_NAME = "setup.exe"
ARCHIVE32_DISTR_NAME = "setup.exe"


FormatMessage = windll.kernel32.FormatMessageA


## Analog of macro MAKELANGID
def MAKELANGID(p, s):
    return (s << 10) | p


LANG_ENGLISH = DWORD(0x0C09)
FORMAT_MESSAGE_FLAGS = DWORD(0x1000 | 0x100 | 0x200)


## Get error string representation.
# @param code Code, returned by GetLastError().
# @return String representation.
def format_message(code):
    buffer = c_char_p()
    FormatMessage(FORMAT_MESSAGE_FLAGS, None, code, MAKELANGID(0x09, 0x01),
                  byref(buffer), 0, None)
    # decode always use ascii cuz FormatMessage called with English language.
    return buffer.value.decode("ascii")


## Get list of process' id by name.
# @param name Name of executable.
# @param filter Additional filter, which used as argument to regex search in cmd.
# @return List of tuples (pid, proc_image, port, full_cmd).
def get_processes_id_by_name(name, filter=None):
    processes_buffer = (DWORD * 100000)()
    bytes_returned = DWORD(0)
    windll.psapi.EnumProcesses(byref(processes_buffer),
                               DWORD(sizeof(processes_buffer)),
                               byref(bytes_returned))
    target_processes = list()
    try:
        procs = execute_wmic_get_command(
            "process", "caption like '%{}%'".format(name),
            "processid,commandline,executablepath", True
        )
    except:
        return []
    # filter founded procs
    for proc in procs:
        if filter is not None and filter not in proc["CommandLine"]:
            continue
        target_processes.append((proc["ProcessId"], proc["ExecutablePath"],
                                 proc["CommandLine"]))
    # log all founded processes
    for proc in target_processes:
        global_logger.debug("found process", name=proc[1], proc_pid=proc[0],
                            cmd=proc[2])
    return target_processes


## Kill process.
# @param pid Process id (PID).
def kill_process(pid):
    handle = windll.kernel32.OpenProcess(DWORD(0x0001), BOOL(True), pid)
    windll.kernel32.TerminateProcess(handle, UINT(-1))
    windll.kernel32.CloseHandle(handle)


## Make dump of process. Dump stored in core.<pid> file.
# @param pid Process id (PID).
# @param mode Mode, which control type of dump. Details here:
#  https://msdn.microsoft.com/en-us/library/windows/desktop/ms680519(v=vs.85).aspx
# @return 0 on success, -1 otherwise.
def make_dump(pid, mode=0x0, folder="."):
    MAXIMUM_ALLOWED = 33554432
    GENERIC_READ = (-2147483648)
    GENERIC_WRITE = 1073741824
    GENERIC_EXECUTE = 536870912
    # build dump file name
    if not os.path.exists(folder):
        os.makedirs(folder)
    dump_file_name = c_char_p(os.path.join(
        folder, "{}.dump".format(pid)
    ).encode(gv.ENCODING))
    # create dump file
    hfile = windll.kernel32.CreateFileA(
        dump_file_name, DWORD(GENERIC_WRITE), DWORD(0), None, DWORD(2),
        DWORD(0x80), None
    )
    # if CreateFile fails, log error and return -1
    if hfile == -1:
        windll.kernel32.CloseHandle(hfile)
        global_logger.warning(message="Fail when creating dump",
                              error=format_message(GetLastError()))
        return -1
    # open process
    handle = windll.kernel32.OpenProcess(DWORD(0x0400 | 0x0010 | 0x0040),
                                         BOOL(True), pid)
    # create dump
    res = windll.dbghelp.MiniDumpWriteDump(handle, pid, hfile, DWORD(mode),
                                           None, None, None)
    # close handles
    windll.kernel32.CloseHandle(hfile)
    # if dump creation fails, delete dump file
    if res == 0:
        windll.kernel32.DeleteFileA(dump_file_name)
        return -1
    windll.kernel32.CloseHandle(handle)
    return 0


## Copy web server extension to specified path
# @param dst Destination path. File name also extracts from here.
# @param setup_folder Source, setup folder of platform.
def copy_web_library(dst, setup_folder):
    l = LogFunc(message="Installing web-extensions", dst=dst)
    dst_head, dst_tail = os.path.split(dst)
    os.makedirs(dst_head, exist_ok=True)
    try:
        shutil.copyfile(os.path.join(setup_folder, dst_tail), dst)
    except shutil.SameFileError as err:
        pass
    except FileNotFoundError:
        try:
            shutil.copyfile(os.path.join(setup_folder, "bin", dst_tail), dst)
        except shutil.SameFileError as err:
            pass


## Get Version property of executable.
# @param fq_path Full path to file.
# @return String with version or None, if version not set.
def get_exe_version(fq_path):
    if not os.path.exists(fq_path):
        return None
    # extract Version property from file
    res = run_cmd(
        "wmic datafile where Name=\"{}\" get Version".format(
            # double backslashes, cuz wmic accept paths with doubled slashes
            fq_path.replace("\\", "\\\\")
        ),
        shell=True
    )
    # extract version value
    re_search = re.search(r"(\d+\.\d+\.\d+\.\d+)",
                          res.stdout.decode(gv.ENCODING), re.MULTILINE)
    # if re_search have groups attribute, then extraction successful
    if hasattr(re_search, "groups"):
        return re_search.groups()[0]
    else:
        return None


## Get version of installed platform.
# @param config lib::common::config::Configuration object.
# @return lib::utils::main::PlatformVersion object.
def get_installed_platform_version(config):
    version = None
    if os.path.exists(os.path.join(config["setup-folder"], "ragent.exe")):
        version = get_exe_version(os.path.join(
            config["setup-folder"], "ragent.exe"
        ))
    else:
        version = get_exe_version(os.path.join(
            config["setup-folder"], "bin", "ragent.exe"
        ))
    if version is None:
        return PlatformVersion(None)
    else:
        return PlatformVersion(version)


## Execute 'wmic <alias> where <conditions> get <properties>' command.
# @param alias Alias for wmic.
# @param conditions String with conditions for wmic.
# @param properties String with comma separated list of necessary properties.
# @param rearrange_result If set, results will be rearranged to list of dicts,
#  which represent row.
# @return CSV-like list of lists, where first list is names of properties
#  (header), and next lists is a rows with values OR list of dicts (rows)
def execute_wmic_get_command(alias, conditions, properties,
                             rearrange_result=False):
    import csv
    # run wmic request
    res = run_cmd("wmic {} where \"{}\" get {} /Format:csv".format(alias,
                                                                   conditions,
                                                                   properties),
                  shell=True)
    # if stderr not empty or returncode is not 0, raise exception
    if len(res.stderr) > 0:
        raise AutomationLibraryError("WMIC_ERROR", res=res)
    if res.returncode != 0:
        raise AutomationLibraryError("WMIC_ERROR", res=res)
    # read stdout to csv
    reader = csv.reader(
        [i for i in res.stdout.decode(gv.ENCODING).splitlines() if len(i) > 0]
    )
    if rearrange_result:
        csv = [i for i in reader]
        result = list()
        for row in csv[1:]:
            item = dict()
            for index in range(0, len(csv[0])):
                item[csv[0][index]] = row[index]
            result.append(item)
        return result
    else:
        return [i for i in reader]


def get_apache_service_name():
    res = execute_wmic_get_command("service", "name like '%apache2%'", "Name",
                                   True)
    if len(res) < 1:
        raise AutomationLibraryError("SERVICE_ERROR",
                                     "cannot find Apache service")
    return res[0]["Name"]


## Return all child processes (recursively), ie child of child of ...
# @param parent_pid Parent PID.
# @return List of PIDs (int).
def get_all_child_procs(parent_pid):
    res = run_cmd(
        "wmic process where (ParentProcessID={}) get ProcessID".format(
            parent_pid
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
    for pid in pids:
        pids += get_all_child_procs(pid)
    return pids


## Kill process and its children.
# @param Process PID.
def kill_process_tree(pid):
    pids = [pid, ] + get_all_child_procs(pid)
    run_cmd("taskkill /f /pid {}".format(
        " /pid ".join([str(pid) for pid in pids])
    ),shell=True)


def regsvr_register_dll(path):
    try_open_file(path)
    res = run_cmd(["regsvr32", "/s", "/i", "/n", path])
    if res.returncode != 0:
        raise AutomationLibraryError(
            "CMD_RESULT_ERROR", args=res.args,
            returncode=res.returncode,
            stdout=res.stdout.decode(gv.ENCODING),
            stderr=res.stderr.decode(gv.ENCODING)
        )

def regsvr_unregister_dll(path):
    try_open_file(path)
    res = run_cmd(["regsvr32", "/s", "/u", path])
    if res.returncode != 0:
        raise AutomationLibraryError(
            "CMD_RESULT_ERROR", args=res.args,
            returncode=res.returncode,
            stdout=res.stdout.decode(gv.ENCODING),
            stderr=res.stderr.decode(gv.ENCODING)
        )
