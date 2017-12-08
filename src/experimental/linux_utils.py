import sys
import os
import shlex
import re
from functools import reduce

PACKAGE_PARENT = '..'
SCRIPT_DIR = os.path.dirname(os.path.realpath(os.path.join(
    os.getcwd(), os.path.expanduser(__file__)
)))
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))


from lib.common import bootstrap
from lib.linux_utils.service import *


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

##List all services in OS.
# @return List of tuples (name, executable, arguments)
def list_services1():
    res = run_cmd(
        "systemctl list-unit-files --type=service -a -f --no-legend --no-pager",
        shell=True
    )
    result_services =  [i.split(" ")[0] for i in res.stdout.decode(gv.ENCODING) \
                       .replace("\r", "").split("\n") if i != ""]
    pairs = []
    for service in result_services:
        res = run_cmd("systemctl show {} -p ExecStart -p FragmentPath".format(
            service.replace("\\", "\\\\")
        ), shell=True)
        # print(service, res.stdout.decode(gv.ENCODING))
        try:
            service = re.sub("\.service$", "", service)
            obj = SystemdService(service)
            obj.connect()
            args = re.sub(obj.exe_name, "", obj.cmd)
            pairs.append((service, obj.exe_name, args))
        except Exception as err:
            # print(err)
            pairs.append((service, "", ""))
    return pairs


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


# @param regex Regex with one group.
# @param s Input string.
# @param default This value will be returned, if found nothing found.
def find_in_str_or_set(regex, s, default=None):
    match = re.search(regex, s)
    if match is None:
        return default
    return match.groups()[0]


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


# @param service_entry Tuple of (name, executable, arguments).
# @return Port.
def parse_ras_service(service_entry):
    port = int(find_in_str_or_set("--port=(\d+)", service_entry[2],
                                  RAS_DEFAULT_PORT))
    return port


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


def is_folder_used_by_1c_services(path):
    used_folders = []
    # check only cluster services
    for i in find_1c_cluster_services():
        used_folders.append(parse_1c_cluster_service(i)[3])
    path = os.path.abspath(os.path.realpath(path))
    for i in used_folders:
        common = os.path.commonprefix([path, i])
        # ie one path contain another or they equal
        if i == common or path == common:
            return True
    return False


def is_name_used_by_services(name):
    for i in list_services():
        if name == i[0]:
            return True
    return False


def can_create_ras_service(name, port=RAS_DEFAULT_PORT):
    return not is_name_used_by_services(name) \
        and not is_port_used_by_1c_services(port)


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
        )


print(is_port_used_by_1c_services(RAS_DEFAULT_PORT) == True)
print(is_port_used_by_1c_services(1563) == True)
print(is_port_used_by_1c_services(CLUSTER_DEFAULT_PORT) == True)
print(is_port_used_by_1c_services(CLUSTER_DEFAULT_REGPORT) == True)
print(is_port_used_by_1c_services(1546) == False)
print(is_folder_used_by_1c_services("/var/test") == False)
print(is_folder_used_by_1c_services("/var/1C/srvinfo") == True)
print(is_folder_used_by_1c_services("/var/1C/srvinfo/test") == True)
print(is_folder_used_by_1c_services("/var") == True)
print(is_name_used_by_services("srv1cv8") \
      == True)
print(is_name_used_by_services("qwe") == False)
print(can_create_ras_service("srv1cv8-ras", 1546) == True)
print(can_create_ras_service("srv1cv8-ras", 1545) == False)
print(can_create_ras_service("srv1cv8-ras", 1560) == False)
print(can_create_1c_cluster_service("1c cluster") == False)
print(can_create_1c_cluster_service("1c cluster", port=1546) == False)
print(can_create_1c_cluster_service("1c cluster", regport=1546) == False)
print(can_create_1c_cluster_service("1c cluster", dyn_range=[1546, ]) == False)
print(can_create_1c_cluster_service("1c cluster", cluster_folder="/var/test") \
      == False)
print(can_create_1c_cluster_service("1c cluster", port=1546, regport=1546,
                                    dyn_range=[1547, 1548],
                                    cluster_folder="/var/test") == False)
print(can_create_1c_cluster_service("1c cluster", port=1546, regport=1547,
                                    dyn_range=[1546, 1548],
                                    cluster_folder="/var/test") == False)
print(can_create_1c_cluster_service("1c cluster", port=1546, regport=1547,
                                    dyn_range=[1547, 1548],
                                    cluster_folder="/var/test") == False)
print(can_create_1c_cluster_service("1c cluster", port=1546, regport=1547,
                                    dyn_range=[1549, 1548],
                                    cluster_folder="/var/test") == True)
