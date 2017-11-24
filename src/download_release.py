# coding: utf-8

import re
import shutil
import os
import cgi
import uuid
import platform
from robobrowser import RoboBrowser


from lib.common import bootstrap
from lib.common.errors import *
from lib.common.logger import *
from lib.utils import *
from lib.utils.cmd import run_cmd
from lib.common import global_vars as gv
from lib.common.config import *


class DownloadReleaseScenario:
    ## Constructor.
    # @param self Pointer to object.
    # @param config lib::common::config::Configuration object.
    # @param kwargs additional named args for config object.
    def __init__(self, config, **kwargs):
        l = LogFunc(message="initializing DownloadReleaseScenario object")
        self.config = config
        # set global test mode variable
        gv.TEST_MODE = self.config["test-mode"]

        # validate configuration
        self.validate_config()
        # set global CONFIG variable
        gv.CONFIG = self.config
        # log self.configuration
        global_logger.debug("Scenario data: " + str(self.config))
        # setting up RoboBrowser object
        self.browser = RoboBrowser(history=True, parser="html.parser")
        nt_version = platform.win32_ver()[1]
        if nt_version != "" and int(nt_version[0]) < 6:
            global_logger.warning(message="Detected Windows version XP or lower"
                                  ". SSL verification disabled due to known "
                                  "bug with it in urllib3.")
            self.browser.session.verify = False
            import urllib3
            urllib3.disable_warnings()
        # create temp dir
        while True:
            try:
                self.config["tmp-folder"] = os.path.join(
                    self.config["tmp-folder"], str(uuid.uuid4())
                )
                os.makedirs(self.config["tmp-folder"])
                break
            except FileExistsError:
                continue
        # create variables
        self.downloaded_file = None
        self.extracted_files = None
        self.extracted_path = None

    ## Validating config.
    # @param self Pointer to object.
    # @exception AutomationLibraryError("OPTION_NOT_FOUND")
    # @exception AutomationLibraryError("ARGS_ERROR")
    def validate_config(self):
        validate_data = [
            ["test-mode", bool],
            ["try-count", int],
            ["timeout", int],
            ["time-limit", int],
            ["download-folder", StrPathExpanded],
            ["tmp-folder", StrPathExpanded],
            ["download-type", str, str, ["data", "url"]],
            ["username", str],
            ["password", str],
            ["additional-data", dict],
        ]
        if self.config["download-type"] == "url":
            validate_data += [
                ["additional-data/url", str],
            ]
        else:
            validate_data += [
                ["release-type", str, str, ["platform", "postgres",
                                            "configuration"]],
            ]
            if self.config["release-type"] == "platform":
                validate_data += [
                    ["additional-data/version", PlatformVersion],
                    ["additional-data/arch", int, int, [64, 32]],
                    ["additional-data/os-type", str, str,
                     ["Windows", "Linux-deb", "Linux-rpm"]],
                    ["additional-data/distr-type", str, str,
                     ["client", "server", "full"]]
                ]
            elif self.config["release-type"] == "postgres":
                validate_data += [
                    ["additional-data/version", str],
                    ["additional-data/arch", int, int, [64, 32]],
                    ["additional-data/os-type", str, str,
                     ["Windows", "Linux-deb", "Linux-rpm"]],
                ]
            else:
                validate_data += [
                    ["additional-data/name", str],
                    ["additional-data/distr-type", str, str,
                     ["full", "update"]],
                    ["additional-data/version", str],
                ]
        self.config.validate(validate_data)

    ## Log into releases.1c.ru portal.
    # @param self Pointer to object.
    def login_to_portal(self):
        l = LogFunc(message="Logging to portal")
        # open portal
        self.browser.open("https://releases.1c.ru/total")
        # get login form
        form = self.browser.get_form(id="loginForm")
        if form is None:
            raise AutomationLibraryError(
                "URL_ERROR", "Cannot find login form. Maybe site structure was"\
                " changed, address is wrong or you already logged in. Try to " \
                "log out and try again. If you keep getting this error, report"\
                " to developer",
                url=self.browser.url
            )
        # fill form
        form["username"] = self.config["username"]
        form["password"] = self.config["password"]
        self.browser.submit_form(form)
        # check, if login successful
        errors = self.browser.find_all(id="credential.errors")
        if len(errors) > 0:
            raise AutomationLibraryError("URL_ERROR", "Login failed",
                                         error=str_tag(errors[0]))

    ## Retrieve URL for downloading 1C:Enterprise Platform of specified version,
    #  arch and OS type.
    # @param version String with version or PlatformversionObject.
    # @param arch Architecture (64 or 32).
    # @param os_type OS type (Windows, Libux-deb, Linux-rpm).
    # @param Distribution type: client, server, all.
    # @return URL for downloading platform.
    def get_platform_url_by_data(self, version, arch, os_type, distr_type):
        l = LogFunc(message="getting platform URL by data", version=version,
                    arch=arch, os_type=os_type)
        # reset browser opened page
        self.browser.open("https://releases.1c.ru/total")
        # set version
        if len(version.version) < 4:
            raise AutomationLibraryError("ARGS_ERROR", "Version incorrect",
                                         current_value=version)
        # get to platform versions page
        self.find_link_and_go(
            "a", "Технологическая платформа {}.{}".format(
                version.version[0], version.version[1]
            )
        )
        # get to specific version page
        self.find_link_and_go("a", "{}".format(version))
        # check input data before usage
        try:
            os_type_str = {
                "Windows": "Windows", "Linux-deb": "DEB", "Linux-rpm": "RPM"
            }[os_type]
        except KeyError:
            raise AutomationLibraryError("ARGS_ERROR", "wrong os type",
                                         value=os_type)
        if arch not in [64, 32]:
            raise AutomationLibraryError("ARGS_ERROR", "wrong architecture",
                                         value=arch)
        # get to download page
        # little workaround for bug 10182776
        if os_type == "Windows" and version < "8.4.1.1":
            global_logger.info(message="OS type and version of platform points "
                               "on version, which is vulnerable to bug 10182776"
                               ", so as workaround would be downloaded full "
                               "distribution of platform", os_type=os_type,
                               version=version)
            regex_filter = "платформа.*{}.*".format(os_type_str)
        else:
            if os_type != "Windows" and distr_type == "full":
                raise AutomationLibraryError(
                    "ARGS_ERROR", "wrong distr type. For Linux distros avaliable"
                    "only 'client' and 'server' types", value=distr_type
                )
            if distr_type == "client":
                regex_filter = "Клиент.*{}.*".format(os_type_str)
            elif distr_type == "server":
                regex_filter = "Сервер.*{}.*".format(os_type_str)
            elif distr_type == "full":
                regex_filter = "платформа.*{}.*".format(os_type_str)
        self.find_link_and_go(
            "a", regex_filter,
            lambda x: "64" in x if arch == 64 else "64" not in x
        )
        # get download link
        return self.find_link("a", "дистр")["href"]

    ## Retrieve URL for downloading PostgreSQL of specified version,
    #  arch and OS type.
    # @param str_version String with version.
    # @param arch Architecture (64 or 32).
    # @param os_type OS type (Windows, Libux-deb, Linux-rpm).
    # @return URL for downloading postgres.
    def get_postgres_url_by_data(self, str_version, arch, os_type):
        def f(s):
            return "одним" in s and "64" in s if arch == 64 else "64" not in s
        l = LogFunc(message="getting postgres URL by data", version=str_version,
                    arch=arch, os_type=os_type)
        # reset browser opened page
        self.browser.open("https://releases.1c.ru/total")
        # get to postgres versions page
        self.find_link_and_go("a", "PostgreSQL")
        # get to specific version page
        self.find_link_and_go("a", "{}".format(str_version))
        # check input data before usage
        try:
            os_type_str = {
                "Windows": "Windows", "Linux-deb": "DEB", "Linux-rpm": "RPM"
            }[os_type]
        except KeyError:
            raise AutomationLibraryError("ARGS_ERROR", "wrong os type",
                                         value=os_type)
        if arch not in [64, 32]:
            raise AutomationLibraryError("ARGS_ERROR", "wrong architecture",
                                         value=arch)
        # get to download page
        self.find_link_and_go("a", ".*{}.*".format(os_type_str), f)
        # get download link
        return self.find_link("a", "дистр")["href"]

    ## Retrieve URL for downloading 1C configuration of specified version,
    #  arch and OS type.
    # @param name Configuration name.
    # @param str_version String with version.
    # @param distr_type Distribution type (full or update).
    # @return URL for downloading configuration.
    def get_configuration_url_by_data(self, name, str_version, distr_type):
        l = LogFunc(message="getting configuration URL by data",
                    name=name, version=str_version, distr_type=distr_type)
        # reset browser opened page
        self.browser.open("https://releases.1c.ru/total")
        # get to configuration versions page
        self.find_link_and_go("a", "^{}$".format(escape_special(name)))
        # get to specific version page
        self.find_link_and_go("a", "{}".format(str_version))
        # get do download page
        if distr_type not in ["update", "full"]:
            raise AutomationLibraryError("ARGS_ERROR",
                                         "wrong configuration distr type",
                                         value=distr_type)
        self.find_link_and_go(
            "a",
            "Дистрибутив обновления" if distr_type == "update" else "Полный"
        )
        # get download link
        return self.find_link("a", "дистр")["href"]

    ## Find tag with link. If found more than one tag, first
    #  found will be returned.
    # @param tag_type Tag type (dv, a, p, etc).
    # @param regex_filter String with regex, which will be used as first filter.
    # @param func_filter Function func(str) -> bool, which will be used as an
    #  additional filter.
    # @return URL.
    # @exception AutomationLibraryError("BROWSER_ERROR") Raised if no tag found.
    def find_link(self, tag_type, regex_filter=None, func_filter=None):
        a = find_tags_by_content(self.browser, tag_type, regex_filter,
                                func_filter)
        if len(a) < 1:
            raise AutomationLibraryError(
                "BROWSER_ERROR", "cannot find tag",
                tag_type=tag_type, regex_filter=regex_filter,
                func_filter=func_filter.__name__ if func_filter else None,
                current_url=self.browser.url
            )
        global_logger.debug(message="Found link", href=a[0]["href"])
        return a[0]

    ## Find href inside tag and follow it. If found more than one tag, first
    #  founded will be used.
    # @param tag_type Tag type (div, a, p, etc).
    # @param regex_filter String with regex, which will be used as first filter.
    # @param func_filter Function func(str) -> bool, which will be used as an
    #  additional filter.
    # @return URL.
    # @exception AutomationLibraryError("BROWSER_ERROR") Raised if no tag found.
    def find_link_and_go(self, tag_type, regex_filter=None, func_filter=None):
        link = self.find_link(tag_type, regex_filter, func_filter)
        self.browser.follow_link(link)

    ## Download product release by data.
    # @param self Pointer to object.
    def download_release_by_data(self):
        if self.config["release-type"] == "platform":
            url = self.get_platform_url_by_data(
                self.config["additional-data"]["version"],
                self.config["additional-data"]["arch"],
                self.config["additional-data"]["os-type"],
                self.config["additional-data"]["distr-type"]
            )
        elif self.config["release-type"] == "postgres":
            url = self.get_postgres_url_by_data(
                self.config["additional-data"]["version"],
                self.config["additional-data"]["arch"],
                self.config["additional-data"]["os-type"],
            )
        elif self.config["release-type"] == "configuration":
            url = self.get_configuration_url_by_data(
                self.config["additional-data"]["name"],
                self.config["additional-data"]["version"],
                self.config["additional-data"]["distr-type"],
            )
        return download_file_from_url_session(self.browser.session, url,
                                              self.config["tmp-folder"])

    ## Process downloaded and extracted files, ie deduce additional data, if
    #  necessary, perform installation and put them in the given path.
    # @param self Pointer to object.
    def process_extracted_file(self):
        l = LogFunc(message="Processing extracted files")
        ### 1. Create download-folder, if it not exist. ###
        if not os.path.exists(self.config["download-folder"]):
            os.makedirs(self.config["download-folder"])
        ### 2. Depend on release-type, process extracted files. ###
        # if release type not specified, set it to None
        if "release-type" not in self.config:
            self.config["release-type"] = None
        # if release type is postgres, just copy files to download-folder
        if self.config["release-type"] == "postgres":
            for f in os.listdir(self.extracted_path):
                f = os.path.join(self.extracted_path, f)
                copy_file_or_directory(f, self.config["download-folder"])
        # if release type is platform, copy files to download-folder/<version>
        elif self.config["release-type"] == "platform":
            dst = os.path.join(self.config["download-folder"],
                               str(self.config["additional-data"]["version"]))
            if not os.path.exists(dst):
                os.makedirs(dst)
            for f in os.listdir(self.extracted_path):
                f = os.path.join(self.extracted_path, f)
                copy_file_or_directory(f, dst)
        elif self.config["release-type"] == "configuration":
            # unpack SFX RAR archive with configuration
            unpack_archive(self.extracted_files[0],
                           self.config["download-folder"])
        # if release type is None, just copy files to download-folder and
        # print warning
        else:
            global_logger.warning(
                message="Download type is unknown, so downloaded file will "
                "be just copied or extracted to download-folder",
                download_folder=self.config["download-folder"]
            )
            copy_file_or_directory(self.extracted_path,
                                   self.config["download-folder"])


    ## Execute scenario.
    # @param self Pointer to object.
    def execute(self):
        ### 0. Login to releases portal. ###
        self.login_to_portal()
        l = LogFunc(message="Downloading release")
        ### 1. Download file ###
        if self.config["download-type"] == "data":
            self.downloaded_file = self.download_release_by_data()
        elif self.config["download-type"] == "url":
            self.downloaded_file = download_file_from_url_session(
                self.browser.session,
                self.config["additional-data"]["url"],
                self.config["tmp-folder"]
            )
        else:
            raise AutomationLibraryError("ARGS_ERROR", "wrong download type",
                                         value=self.config["download-type"])
        ### 2. Extract file (or just move, if its not archive) ###
        # get file name and file extension
        filename, ext = splitext_archive(self.downloaded_file)
        self.extracted_path = os.path.join(self.config["tmp-folder"],
                                      "extracted")
        # create extracted_path, if it not exists
        if not os.path.exists(self.extracted_path):
            os.makedirs(self.extracted_path)
        # if downloaded file have archive extension, then extract it
        if ext in [".rar", ".tar.gz", ".tar", ".tar.bz2", ".tar.xz", ".zip"]:
            self.extracted_files = unpack_archive(self.downloaded_file,
                                                  self.extracted_path)

        # if not, just copy it
        else:
            copy_file_or_directory(self.downloaded_file, self.extracted_path)
            self.extracted_files = [self.downloaded_file, ]
        ### 3. Complete additional data, if necessary ###
        if self.config["download-type"] == "url":
            self.fill_additional_data()
        ### 4. Process extracted files. ###
        self.process_extracted_file()

    ## Deduce release type and set it in self.config. If cannot deduce, set it
    #  to None.
    # @param self Pointer to object.
    def deduce_release_type(self):
        filename, ext = splitext_archive(os.path.basename(self.downloaded_file))
        # if "postgres" in file name, assume that we downloaded postgres
        if "postgres" in filename:
            self.config["release-type"] = "postgres"
        # if downloaded file is executable, then assume that we downloaded
        # configuration installer
        elif ext == ".exe":
            self.config["release-type"] = "configuration"
            # set distr-type
            if filename == "updsetup":
                self.config["additional-data"]["distr-type"] = "update"
            else:
                self.config["additional-data"]["distr-type"] = "full"
        # if file name in this list, then assume that we downloaded platform
        elif filename in ["deb", "deb64", "rpm", "rpm64", "windows",
                          "windows64"]:
            self.config["release-type"] = "platform"
            # set os-type
            if filename in ["windows", "windows64"]:
                self.config["additional-data"]["os-type"] = "Windows"
            elif filename in ["deb", "deb64"]:
                self.config["additional-data"]["os-type"] = "Linux-deb"
            elif filename in ["rpm", "rpm64"]:
                self.config["additional-data"]["os-type"] = "Linux-rpm"
            # set arch
            if "64" in filename:
                self.config["additional-data"]["arch"] = 64
            else:
                self.config["additional-data"]["arch"] = 32
        else:
            self.config["release-type"] = None
            global_logger.warning(
                message="Cannot deduce download type. Proceed without it"
            )

    ## Deduce platform version and set it in self.config. If cannot deduce, set
    #  it to None.
    # @param self Pointer to object.
    def deduce_platform_version(self):
        # get platform version. If os is Windows, extract property from
        # setup.exe
        if self.config["additional-data"]["os-type"] == "Windows":
            try:
                import configparser
                config = configparser.ConfigParser()
                config.read(os.path.join(self.extracted_path, "Setup.ini"))
                version = config["Startup"]["ProductVersion"]
            except:
                version = None
        # if os is not Windows, ie Linux, then extract version from archive
        # name
        else:
            try:
                # get name of any archive
                archive = [
                    f for f in self.extracted_files \
                    if splitext_archive(f)[1] in [".deb", ".rpm"]
                ][0]
                version = re.search("(\\d+\.\\d+\.\\d+-\\d+)",
                                    archive).groups()[0]
                print(re.search("(\\d+\.\\d+\.\\d+-\\d+)",
                                archive))
            except:
                version = None
                # if version not found, proceed without it.
        if version is None:
            global_logger.warning(
                message="Cannot extract version of platform distr."
            )
        self.config["additional-data"]["version"] = str(PlatformVersion(
            version
        ))

    ## Fill additional data in self.config.
    # @param self Pointer to object.
    def fill_additional_data(self):
        ### 1. Deduce release type. ###
        if "release-type" not in self.config:
            self.deduce_release_type()
        ### 2. Deduce release type specific details. ###
        if self.config["release-type"] == "postgres":
            return
        elif self.config["release-type"] == "platform":
            print(self.config["additional-data"])
            if "version" not in self.config["additional-data"]:
                self.deduce_platform_version()
        elif self.config["release-type"] == "configuration":
            pass


## Return tag content as string.
# @param tag Tag object.
# @return Tag string representation.
def str_tag(tag):
    return "".join([str(i) for i in tag.contents])


## Find tags on HTML page.
# @param browser RoboBrowser object with opened page, where search should be
#  performed.
# @param tag_type Tag type (dv, a, p, etc).
# @param regex_filter String with regex, which will be used as first filter.
# @param func_filter Function func(str) -> bool, which will be used as an
#  additional filter.
# @return List with tag objects.
def find_tags_by_content(browser, tag_type, regex_filter=None,
                         func_filter=None):
    # find all tags with tag_type
    tags = browser.find_all(tag_type)
    # filter tags with regex
    if regex_filter is not None:
        # replace similar symbols in regex
        regex_filter = replace_similar_symbols(regex_filter)
        global_logger.debug(message="Filtering tags by regex",
                            regex=regex_filter)
        tags = [i for i in tags \
                if re.search(regex_filter, str_tag(i)) is not None]
    # filter tags with function
    if func_filter is not None:
        tags = [i for i in tags \
                if func_filter(str_tag(i))]
    return tags


## Download file from url and session.
# @param session Session object. This session might be used for download files
#  from site, which require login or some specific cookies.
# @param url Source URL.
# @param dst Destination folder.
# @param extract_filename_from_response If True, file name will be extracted
#  from response header. If extraction fails, file name will be random UUID.
#  If False, dst_filename arg used as file name (and UUID, if dst_filename not
#  set).
# @param dst_filename File name, which will be used if
#  extract_filename_from_response is False.
# @return Path to downloaded file.
def download_file_from_url_session(session, url, dst,
                                   extract_filename_from_response=True,
                                   dst_filename=None):
    l = LogFunc(message="Downloading file", src=url, dst=dst)
    response = session.get(url, stream=True)
    # build dst full path
    # if extract_filename_from_response is True, try to extract file
    # name from response. If fail, set it to random UUID.
    if extract_filename_from_response == True:
        name = get_filename_from_response(response)
        if name is None:
            name = str(uuid.uuid4())
    # if not, get file name from dst_filename argument. If it is None,
    # set file name to random UUID.
    else:
        name = dst_filename if dst_filename is not None else str(uuid.uuid4)
    file_path = os.path.join(dst, name)
    # perform copy
    with open(file_path, "wb") as f:
        shutil.copyfileobj(response.raw, f)
    return file_path


## Extract filename filed from response headers.
# @param response Response object.
# @return String with file name or None, if filename not presented.
def get_filename_from_response(response):
    header = response.headers["Content-Disposition"]
    value, params = cgi.parse_header(header)
    if "filename" in params:
        return params["filename"]
    else:
        return None


## Wrapper for scenario execution.
# @return Last error code (0 if no errors occurred).
def download_release_scenario():
    res = 1
    # execute scenario
    try:
        data = read_yaml(sys.argv[1])
        config = ScenarioConfiguration(data)
        cmd_args = bootstrap.parse_cmd_args(sys.argv[2:])
        config.add_cmd_args(cmd_args[1], True)
        bootstrap.set_debug_values(cmd_args[1])
        scenario = DownloadReleaseScenario(config)
        scenario.execute()
    # handle errors (ie log them and set return code)
    except AutomationLibraryError as err:
        global_logger.error(
            str(err), state="error",
        )
        res = err.num_code
    except Exception as err:
        err = AutomationLibraryError("UNKNOWN", err)
        global_logger.error(
            str(err), state="error",
        )
        res = err.num_code
    # and if no errors occurred, set return code to 0
    else:
        res = 0
    return res


if __name__ == "__main__":
    bootstrap.main(download_release_scenario,
                   os.path.basename(__file__)[0:-3])
