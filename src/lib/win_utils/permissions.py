import winreg
from ctypes import *
from ctypes.wintypes import *

from ..common import global_vars as gv
from ..common.errors import AutomationLibraryError
from ..utils.cmd import run_cmd

RegOpenKeyEx = windll.advapi32.RegOpenKeyExA
AllocateAndInitializeSid = windll.advapi32.AllocateAndInitializeSid
CheckTokenMembership = windll.advapi32.CheckTokenMembership
FreeSid = windll.advapi32.FreeSid

SID_IDENTIFIER_AUTHORITY = c_ubyte * 6
SECURITY_NT_AUTHORITY = (0, 0, 0, 0, 0, 5)
DOMAIN_ALIAS_RID_ADMINS = 0x220
SECURITY_BUILTIN_DOMAIN_RID = 32


## Check AlwaysInstallElevated registry key.
# @return True or False.
def check_always_elevated_update():
    # check AlwaysInstallElevated key
    AlwaysInstallElevated = False
    try:
        AlwaysInstallElevated = True if winreg.QueryValueEx(winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            "Software\\Policies\\Microsoft\\Windows\\UpdatePlatform"
        ), "AlwaysInstallElevated") == 1 else False
    except OSError as e:
        pass
    return AlwaysInstallElevated


## Check, if current user is Administrator.
# @return True or False.
def test_is_admin():  # copied from https://msdn.microsoft.com/en-us/library/windows/desktop/aa376389(v=vs.85).aspx
    nt_authority = SID_IDENTIFIER_AUTHORITY(*SECURITY_NT_AUTHORITY)
    administrators_group = LPVOID()
    # allocate and initialize administrators_group
    b = BOOL(AllocateAndInitializeSid(byref(nt_authority), 2,
                                      SECURITY_BUILTIN_DOMAIN_RID,
                                      DOMAIN_ALIAS_RID_ADMINS,
                                      0, 0, 0, 0, 0, 0,
                                      byref(administrators_group)))
    # check Administrator token
    if b is True:
        if not CheckTokenMembership(None, administrators_group, PBOOL(b)):
            b = BOOL(False)
            FreeSid(administrators_group)
    return bool(b)
