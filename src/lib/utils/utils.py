# coding: utf-8

import hashlib
import io
import os
import platform
import re
import shutil
import yaml
import sys
from distutils.dir_util import copy_tree, remove_tree
from multiprocessing import Process, Queue
from itertools import islice
import collections


from .cmd import run_cmd
from ..common import global_vars as gv
from ..common.errors import AutomationLibraryError
from ..common.logger import global_logger, LogFunc


## Class, represents platform version.
class PlatformVersion:

    ## Constructor.
    # @param self Pointer to object.
    # @param version Version. Can be string, None or another PlatformVersion
    #  object.
    def __init__(self, version):
        if version is None:
            self.version = ()
            return
        if isinstance(version, PlatformVersion):
            self.version = version.version
            return
        self.version = tuple(re.findall(r"\d+", version))

    ## String representation of object for Linux.
    # @param self Pointer to object.
    def str_linux(self):
        return "{}.{}.{}-{}".format(*self.version) if len(self.version) > 0 \
            else ""

    ## String representation of object.
    # @param self Pointer to object.
    def __str__(self):
        return ".".join(self.version) if len(self.version) > 0 \
            else ""

    ## Debug representation of object for Linux.
    # @param self Pointer to object.
    def __repr__(self):
        return "PlatformVersion: " + str(self.version)

    ## Get part of version by index.
    # @param self Pointer to object.
    def __getitem__(self, index):
        return self.version[index]

    ## Compare object with other version.
    # @param self Pointer to object.
    # @param other Object, which represent version. Should be str or
    #  lib::utils::main::PlatformVersion object.
    # @return True, False or None, if object is not a str or
    #  lib::utils::main::PlatformVersion
    def __eq__(self, other):
        if isinstance(other, PlatformVersion):
            return self.version == other.version
        elif isinstance(other, str):
            return self.version == PlatformVersion(other).version
        elif isinstance(other, type(None)):
            return self.version == PlatformVersion(other).version
        else:
            return None

    def __gt__(self, other):
        if isinstance(other, str):
            other = PlatformVersion(other)
        elif isinstance(other, type(None)):
            return None
        for i in range(0, min(len(self.version), len(other.version))):
            if int(self.version[i]) > int(other.version[i]):
                return True
        if len(self.version) > len(other.version):
            return True
        return False

    def __lt__(self, other):
        if isinstance(other, str):
            other = PlatformVersion(other)
        elif isinstance(other, type(None)):
            return None
        for i in range(0, min(len(self.version), len(other.version))):
            if int(self.version[i]) < int(other.version[i]):
                return True
        if len(self.version) < len(other.version):
            return True
        return False


## Dummy function.
# @param *args Ignored.
# @param **kwargs Ignored.
# @return None.
def dummy(*args, **kwargs):
    return None


## Decorator, which allow to add function a static variables like in C++.
#  Static variables stored in function_name.__static_vars__ object.
# @param Name of the variable.
# @param initial_value Value, which this variable will have initial.
def static_var(name, initial_value=None):
    def wrapper(func):
        if not hasattr(func, "__static_vars__"):
            setattr(func, "__static_vars__", type('__static_vars__', (), {})())
        setattr(func.__static_vars__, name, initial_value)
        return func
    return wrapper


## Check, if current platform is 64 bit.
# @return True or False.
# @exception AutomationLibraryError("NO_ARCHITECTURE") Raised if cannot detect
#  platform architecture.
def is_64bit_arch():
    bit32id = ["32bit", "x86"]
    bit64id = ["64bit", "x86_64", "AMD64"]
    bit_ids = bit32id + bit64id

    # trying to retrieve platform architecture in different ways
    res = platform.machine()
    if res not in bit_ids:
        res = platform.processor()
    else:
        return res in bit64id
    if res not in bit_ids:
        res = platform.architecture()
    else:
        return res in bit64id
    for i in res:
        if i in bit_ids:
            res = i
            return res in bit64id
    raise AutomationLibraryError("NO_ARCHITECTURE")


## Try to open file and convert exceptions to AutomationLibraryError.
# @param path Path to file.
# @param mode Mode.
# @param should_exist Should file exist. If set to False, file will be created,
#  if it doesn't exist, and removed. It can be useful to check, can file,
#  specified by path argument, be created.
# @exception AutomationLibraryError(*)
def try_open_file(path, mode="r", should_exist=True):
    delete_on_exit = False
    try:
        # if file not exist and shouldn't, then create it and delete on exit
        if not os.path.exists(path) and not should_exist:
            delete_on_exit = True
            f = open(path, "w")
        else:
            f = open(path, mode)
    # handle exceptions
    except FileNotFoundError:
        raise AutomationLibraryError("FILE_NOT_EXIST", path)
    except PermissionError:
        raise AutomationLibraryError("FILE_PERM_DENIED", path)
    except Exception as e:
        raise AutomationLibraryError("UNKNOWN", str(e))
    else:
        f.close()
    # if set delete_on_exit, then delete file
    if delete_on_exit:
        try:
            os.remove(path)
        except Exception:
            pass


## Open file and convert exceptions to AutomationLibraryError.
# @param path Path to file.
# @param mode Mode.
# @return file object.
# @exception AutomationLibraryError(*)
def open_file(path, mode="r", encoding="utf-8"):
    try:
        f = open(path, mode=mode, encoding=encoding)
    except FileNotFoundError as e:
        raise AutomationLibraryError("FILE_NOT_EXIST", path)
    except PermissionError as e:
        raise AutomationLibraryError("FILE_PERM_DENIED", path)
    except Exception as e:
        raise AutomationLibraryError("UNKNOWN", e)
    else:
        return f


## Open and read YAML file.
# @param path Path to YAML file.
# @return Content of YAML file.
# @exception AutomationLibraryError("YAML_PROBLEM_MARK") Incorrect syntax.
# @exception AutomationLibraryError("YAML_COMMON_ERROR") Unknown error while
#  processing YAML file.
def read_yaml(path):
    try:
        f = open_file(path, encoding="utf-8")
        data = yaml.load(f)
    except yaml.YAMLError as err:
        if hasattr(err, "problem_mark"):
            mark = err.problem_mark
            raise AutomationLibraryError("YAML_PROBLEM_MARK",
                                         mark.line + 1, mark.column + 1,
                                         str(err), path)
        else:
            raise AutomationLibraryError("YAML_COMMON_ERROR",
                                         str(err), path)
    f.close()
    return data


## Detect OS type.
# @return one of values: "Windows", "Linux-deb", "Linux-rpm".
# @exception AutomationLibraryError("UNKNOWN", "OS not supported")
def detect_actual_os_type():
    os_str = platform.system()
    if os_str not in ["Windows", "Linux"]:
        raise AutomationLibraryError("UNKNOWN", "OS not supported")

    if os_str == "Linux":
        linux_type = "deb" if run_cmd("dpkg --version", shell=True) \
            .returncode == 0 else "rpm"
        return os_str + "-" + linux_type
    else:
        return os_str


# .exe for SFX RAR doesn't included cuz it also could be just executable
# file. If you sure that .exe is SFX, then add it yourself
KNOWN_ARCHIVE_EXTENSIONS = [".rar", ".zip", ".tar.gz", ".tar.xz", ".tar.bz2",
                            ".tar"]


## Trying to split filename to name and archive extension. If known
#  archive extension (like .tar.gz) not found, acts like an os.path.splitext().
#  If file name contain only archive extensions, like ".tar.gz", then all
#  (2 in this case) extensions considers as one whole, and will be returned as
#  (".tar.gz", "") for this case.
# @param path Path to file.
# @param additional_exts List of extensions, which you would like to also
#  process in special way.
# @param replace_exts If True, replace known extensions with additional_exts
#  instead of adding them to already known.
# @return String with extension.
def splitext_archive(path, additional_exts=[], replace_exts=False):
    # get file name with extension
    folder, filename = os.path.split(path)
    # list of known extensions
    if replace_exts:
        known_extensions = additional_exts
    else:
        known_extensions = KNOWN_ARCHIVE_EXTENSIONS \
                           + list(additional_exts)
    for ext in known_extensions:
        if ext == filename[len(filename)-len(ext):]:
            if ext == filename:
                return ext, ""
            return os.path.join(folder, filename.replace(ext, "")), ext
    return os.path.splitext(path)


## Unpack archive. Type of archive is determined by its extension.
# @param path Path to archive file.
# @param dst Destination folder.
# @return List of extracted files.
def unpack_archive(path, dst):
    l = LogFunc(message="Unpacking archive", src=path, dst=dst)
    _, archive_ext = splitext_archive(path)
    unpack_functions = {
        ".exe": unpack_sfx_rar,
        ".rar": unpack_rar,
        ".zip": unpack_zip,
        ".tar": unpack_tar,
        ".tar.gz": unpack_gztar,
        ".tar.xz": unpack_xztar,
        ".tar.bz2": unpack_bz2tar,
    }
    try:
        return unpack_functions[archive_ext](path, dst)
    except KeyError as err:
        raise ValueError("Unsupported file extension.")


## Unpack RAR archive. Also try to unpack it as SFX archive.
# @param path Path to archive file.
# @param dst Destination folder.
# @return List of extracted files.
def unpack_rar(path, dst):
    import rarfile
    rarfile.UNRAR_TOOL = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
        "external_utils", "unrar",
        "unrar.exe" if platform.system() == "Windows" else "unrar"
    )
    archive = rarfile.RarFile(path)
    files = archive.namelist()
    archive.extractall(dst)
    return list([os.path.join(dst, f) for f in files])


def unpack_sfx_rar(path, dst):
    import rarfile
    import tempfile
    rarfile.UNRAR_TOOL = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
        "external_utils", "unrar",
        "unrar.exe" if platform.system() == "Windows" else "unrar"
    )
    # first check, that path is actually SFX RAR archive
    if run_cmd([rarfile.UNRAR_TOOL, "t", path]).returncode != 0:
            raise AutomationLibraryError("UNPACK_ERROR", "bad SFX RAR archive",
                                         path=path)
    # perform extraction to temp folder
    tmp_folder = tempfile.mkdtemp()
    global_logger.debug(message="Created temporary folder", path=tmp_folder)
    res = run_cmd([rarfile.UNRAR_TOOL, "x", path, os.path.join(tmp_folder, "")])
    # if not successful, raise an error
    if res.returncode != 0:
        raise AutomationLibraryError("UNPACK_ERROR",
                                     "error while extracting SFX archive",
                                     path=path)
    # copy files from temporary location to dst
    copy_file_or_directory(tmp_folder, dst, False)
    # if successful, store all file names and relative paths
    files = []
    for root, dirnames, filenames in os.walk(tmp_folder):
        for filename in filenames:
            # replace temp folder part with nothing, for create relative paths
            rel_file_path = os.path.join(root, filename) \
                                   .replace(os.path.join(tmp_folder, ""), "")
            files.append(os.path.join(dst, rel_file_path))
    # remove tmp_folder
    remove_tree(tmp_folder)
    return files


def unpack_zip(path, dst, try_encode=None):
    import zipfile
    archive = zipfile.ZipFile(path, "r")
    files = []
    for fileinfo in archive.infolist():
        # fix
        if try_encode is not None:
            try:
                file_path = fileinfo.filename.encode("cp437").decode(try_encode)
            except:
                file_path = fileinfo.filename
        else:
            file_path = fileinfo.filename
        try:
            os.makedirs(os.path.split(os.path.join(dst, file_path))[0])
        except:
            pass
        shutil.copyfileobj(archive.open(fileinfo),
                           open(os.path.join(dst, file_path), "w+b"))
        files.append(file_path)
    return list([os.path.join(dst, f) for f in files])


## Unpack TAR archive.
# @param path Path to archive file.
# @param dst Destination folder.
# @return List of extracted files.
def unpack_tar(path, dst):
    import tarfile
    archive = tarfile.open(path, "r:")
    files = archive.getnames()
    archive.extractall(dst)
    return list([os.path.join(dst, f) for f in files])


## Unpack GZTAR archive.
# @param path Path to archive file.
# @param dst Destination folder.
# @return List of extracted files.
def unpack_gztar(path, dst):
    import tarfile
    archive = tarfile.open(path, "r:gz")
    files = archive.getnames()
    archive.extractall(dst)
    return list([os.path.join(dst, f) for f in files])


## Unpack XZTAR archive.
# @param path Path to archive file.
# @param dst Destination folder.
# @return List of extracted files.
def unpack_xztar(path, dst):
    import tarfile
    archive = tarfile.open(path, "r:xz")
    files = archive.getnames()
    archive.extractall(dst)
    return list([os.path.join(dst, f) for f in files])


## Unpack BZ2TAR archive.
# @param path Path to archive file.
# @param dst Destination folder.
# @return List of extracted files.
def unpack_bz2tar(path, dst):
    import tarfile
    archive = tarfile.open(path, "r:bz2")
    files = archive.getnames()
    archive.extractall(dst)
    return list([os.path.join(dst, f) for f in files])


## Detect installation type of 1C:Enterprise platform.
# @param archive_name Name of archive, which needed by archive type of
#  installation
# @param folder Path to distr folder.
# @return "setup" or "copy"
def detect_installation_type(archive_name, folder):
    file_path = os.path.join(folder, archive_name)
    return "setup" if os.path.isfile(file_path) else "copy"


## Compute hash of files and directories recursively.
# @param paths List of paths, that should be included to hash calculation.
# @return MD5 hash.
def compute_recursive_hash(paths):
    _f = LogFunc(message="calculating hash", paths=paths)

    ## Calculate hash of file.
    def update_hash_from_file(file_path, hash_obj):
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_obj

    ## Calculate hash over directory.
    def update_hash_from_folder(path, hash_obj):
        for entry in os.listdir(path):
            if os.path.isdir(os.path.join(path, entry)):
                hash_obj = update_hash_from_folder(
                    os.path.join(path, entry),
                    hash_obj
                )
            else:
                hash_obj = update_hash_from_file(
                    os.path.join(path, entry),
                    hash_obj
                )
        return hash_obj

    hash_md5 = hashlib.md5()
    # apply hash functions to all paths
    for path in paths:
        if os.path.isdir(path):
            hash_md5 = update_hash_from_folder(path, hash_md5)
        else:
            hash_md5 = update_hash_from_file(path, hash_md5)
    return hash_md5.hexdigest()


## Walk over dictionary and apply function to all leaves.
# @param node Dictionary.
# @param func Function, that should accept leaf value and return value, that
#  will be set to leaf.
# @param pass_key Should key be passed to func as second arg or not.
def apply_to_leaves(node, func, pass_key=False):
    for key, value in node.items():
        if hasattr(value, "items"):
            apply_to_leaves(value, func, pass_key)
        else:
            if pass_key:
                node[key] = func(value, key)
            else:
                node[key] = func(value)


## Check, if path is a correct path in FS (ie can it be used in open() function).
# @param path String with path.
# @return True, False or None (if check fails).
def is_os_path(path):
    try:
        f = open(path, "r")
        f.close()
    except OSError as err:
        if err.errno == 22:
            return False
    except Exception:
        return None
    return True


## Copy directory tree or file from src to dst, overwrite old data.
# @param src Source path.
# @param dst Destination path (directory).
# @param copy_dir_with_root If True, on copy directory act like
#  distutils.dir_util.copy_tree, ie all files in src will be in dst.
# @exception ValueError If src either not directory and file.
def copy_file_or_directory(src, dst, copy_dir_with_root=True):
    if os.path.isdir(src):
        # cut last folder from src
        if copy_dir_with_root:
            src_dir = os.path.basename(src)
            dst_dir = os.path.join(dst, src_dir)
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)
            copy_tree(src, dst_dir)
        else:
            copy_tree(src, dst)
    elif os.path.isfile(src):
        shutil.copy(src, dst)
    else:
        raise ValueError("'src' must be a file or directory")


## Return regex for matching symbols, which appears similarly in latin (English)
#  and cyrrilic (Russian) alphabets.
# @param char Symbol.
# @return Regex with both (latin and cyrrilic) symbols, if it appears similarly
#  or just symbol, if it is unique.
def get_regex_for_similar_char(char):
    latin    = "A a B C c E e H K k M O o P p T X x".split(" ")
    cyrrilic = "А а В С с Е е Н К к М О о Р р Т Х х".split(" ")
    blank = "(?:{}|{})"
    index = None
    if char in latin:
        index = latin.index(char)
    if char in cyrrilic:
        index = cyrrilic.index(char)
    return char if index is None else blank.format(latin[index],
                                                   cyrrilic[index])


## Replace in regex symbols, which appears similarly in latin (English)
#  and cyrrilic (Russian) alphabets, with regex like (?:x|х).
# @param regex Input regex string.
# @return Regex with replaced symbols.
def replace_similar_symbols(regex):
    output = ""
    for char in regex:
        output += get_regex_for_similar_char(char)
    return output


## Replace in regex special symbols with escaped sequences.
# @param regex Input regex string.
# @param additional_symbols Additional symbols, which should be escaped.
# @return Regex string with escaped symbols.
def escape_special(regex, additional_symbols=[]):
    to_replace = ". ( ) \\".split(" ") + additional_symbols
    result = ""
    for sym in regex:
        if sym in to_replace:
            result += "\\" + sym
        else:
            result += sym
    return result


## Advance the iterator n-steps ahead. If n is none, consume entirely.
def consume(iterator, n):
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        collections.deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(islice(iterator, n, n), None)
