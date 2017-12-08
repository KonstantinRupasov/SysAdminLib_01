# coding: utf-8

import os
import re
import shutil
import subprocess as sp

from ..common import global_vars as gv
from ..common.errors import AutomationLibraryError
from ..common.logger import global_logger, LogFunc
from ..utils.cmd import run_cmd


## Copy web server extension to specified path
# @param dst Destination path. File name also extracts from here.
# @param setup_folder Source, setup folder of platform.
def copy_web_library(dst, setup_folder):
    l = LogFunc(message="Installing web-extensions", dst=dst)
    dst_head, dst_tail = os.path.split(dst)
    res = run_cmd(["find", "/opt", "-iname", dst_tail])
    if res.returncode:
        raise AutomationLibraryError(
            "INSTALL_ERROR", "cannot find web library")
    src = res.stdout.decode(gv.ENCODING).split()[0]
    try:
        shutil.copyfile(src, dst)
    except shutil.SameFileError as err:
        pass


## Get list of process' id by name.
# @param name Name of executable..
# @param filter Additional filter, which used as argument to grep.
# @return List of tuples (pid, proc_image, full_cmd).
def get_processes_id_by_name(name, filter=None):
    # find processes with specified name and filter, if necesary
    cmd = "ps -eo pid,command --no-header | grep -i \"{}\"".format(
        os.path.basename(name)
    ) + (
        " | grep -i {}".format(filter)
        if filter is not None else ""
    ) + (
        " | grep -i {}".format(os.path.dirname(name))
        if os.path.dirname(name) != "" else ""
    ) + " | grep -v grep"
    res = run_cmd(cmd, shell=True)
    # gather results to list
    processes = [tuple(i.split())
                 for i in res.stdout.decode(gv.ENCODING).split("\n")][:-1]
    result = []
    for proc in processes:
        result.append(tuple([int(proc[0]), proc[1], " ".join(proc[1:])]))
        global_logger.info("found process", name=proc[1], proc_pid=proc[0])
    return result


## Detecting Apache service name.
# @return String with service name.
def get_apache_service_name():
    l = LogFunc(message="detecting apache service name")
    return "apache2"


## Return all child processes (recursively), ie child of child of ...
# @param parent_pid Parent PID.
# @return List of PIDs (int).
def get_all_child_procs(parent_pid):
    pids = [int(pid) for pid in run_cmd(["pgrep", "-P", str(parent_pid)]) \
            .stdout.decode(gv.ENCODING).split("\n")[:-1]]
    for pid in pids:
        pids += get_all_child_procs(pid)
    return pids


## Kill process and its children.
# @param Process PID.
def kill_process_tree(pid):
    pids = [pid, ] + get_all_child_procs(pid)
    run_cmd("kill -9 {}".format(" ".join([str(pid) for pid in pids])),
            shell=True)
