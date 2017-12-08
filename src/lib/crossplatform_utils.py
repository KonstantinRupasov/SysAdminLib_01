import os


from .common.errors import *
from .common.logger import *
from .common.config import *
from .utils import *


actual_os = detect_actual_os_type()
if actual_os == "Windows":
    from lib import win_utils as os_utils
else:
    from lib import linux_utils as os_utils

# from os_utils.service import *
# from os_utils import *


def number_of_ragent_processes_running(folder=""):
    ragent_path = os.path.join(folder, "ragent")
    ragent_procs = list()
    if actual_os == "Windows":
        from lib.win_utils import get_processes_id_by_name
        ragent_procs = get_processes_id_by_name(
            "ragent.exe",
            repr(folder)[1:-1]
        ) if folder != "" else get_processes_id_by_name(
            "ragent.exe",
        )
    else:
        from lib.linux_utils import get_processes_id_by_name
        ragent_procs = get_processes_id_by_name(ragent_path)
    return len(ragent_procs)
