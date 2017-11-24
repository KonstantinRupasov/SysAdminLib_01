import platform

if platform.system() == "Linux":
    from .linux_utils import *
