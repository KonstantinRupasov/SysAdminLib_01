import platform

if platform.system() == "Windows":
    from .win_utils import *
