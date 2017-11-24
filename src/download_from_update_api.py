# coding: utf-8

import requests
import json
import cgi
import base64
import uuid
import os
import tempfile
import pathlib
import hashlib


from lib.common import bootstrap
from lib.common.errors import *
from lib.common.logger import *
from lib.utils import *
from lib.utils.cmd import run_cmd
from lib.common import global_vars as gv
from lib.common.config import *


BASE_PATH = "https://update-api.1c.ru/update-platform/programs/update/"


## Convert dictionary to list of {key: value}.
# @param data Dictionary.
# @return list of {key: value}.
def dict_to_key_value_pair_list(data):
    return [{"key": key, "value": value} for key, value in data.items()]


## Make {basePath}/info request.
# @param config_name Name of configuration in update-api service.
# @param config_version Current version of configuration.
# @param additional_parameters Dictionary with additional_parameters.
# @return requests.Response object.
def info_request(config_name, config_version, additional_parameters={}):
    l = LogFunc(message="Making Info request", config_name=config_name,
                current_version=config_version,
                additional_parameters=additional_parameters)
    # fill JSON data
    json_data = {
        "programName": config_name,
        "versionNumber": config_version,
        "platformVersion": "",
        "programNewName": "",
        "redactionNumber": "",
        "updateType": "NewConfigurationAndOrPlatform",
        "additionalParameters": dict_to_key_value_pair_list(
            additional_parameters
        )
    }
    # make request
    response = requests.post(
        BASE_PATH + "info/", data=json.dumps(json_data),
        headers={
            "User-Agent": "1C+Enterprise/8.3",
            "Content-Type": "application/json",
            "Accept": "*/*"
        }
    )
    global_logger.debug(message="Info response", http_code=response.status_code,
                        headers=response.headers,content=response.content)
    # if response contain JSON data, return it, raise exception otherwise
    if response.ok and "application/json" in \
       cgi.parse_header(response.headers["Content-Type"]):
        return response
    else:
        raise AutomationLibraryError("NOT_JSON", content=response.content)


## Make {BasePath}/ request.
# @param info_response requests.Response object, which returned by info_request().
# @param username Name of user on portal.1c.ru.
# @param password Password of user on portal.1c.ru.
# @param additional_parameters Dictionary with additional_parameters.
# @return requests.Response object.
def get_files_request(info_response, username, password,
                      additional_parameters={}):
    # extract upgrade sequence
    try:
        upgrade_sequence = info_response.json()["configurationUpdateResponse"] \
                   ["upgradeSequence"]
        if len(upgrade_sequence) < 1:
            raise AutomationLibraryError("ARGS_ERROR",
                                         "upgrade UUIDS not found",
                                         value=info_response.content)
    except:
        raise AutomationLibraryError("ARGS_ERROR",
                                     "upgrade UUIDS not found",
                                     value=info_response.content)
    # extract current uuid
    try:
        current_uuid = info_response.json()["configurationUpdateResponse"] \
                   ["programVersionUin"]
    except:
        raise AutomationLibraryError("ARGS_ERROR",
                                     "current version UUID not found",
                                     value=info_response.content)
    l = LogFunc(message="Making GetFiles request",
                upgrade_sequence=upgrade_sequence,
                current_uuid=current_uuid,
                additional_parameters=additional_parameters)
    # fill JSON data
    json_data = {
        "upgradeSequence": upgrade_sequence,
        "programVersionUin": current_uuid,
        "login": username,
        "password": password,
        "platformDistributionUin": None,
        "additionalParameters": dict_to_key_value_pair_list(
            additional_parameters
        )
    }
    # make request
    response = requests.post(BASE_PATH, data=json.dumps(json_data),
        headers={
            "User-Agent": "1C+Enterprise/8.3",
            "Content-Type": "application/json",
            "Accept": "*/*"
        }
    )
    global_logger.debug(message="Get files response",
                        http_code=response.status_code,
                        headers=response.headers,content=response.content)
    # if response contain JSON data, return it, raise exception otherwise
    if response.ok and "application/json" in \
       cgi.parse_header(response.headers["Content-Type"]):
        return response
    else:
        raise AutomationLibraryError("NOT_JSON", content=response.content)


## Download and extract update file. Also performs comparison of hash sums.
# @param configuration_update_entry Element of
#  GetFilesResponse["configurationUpdateDataList"].
# @param store_location Path, where updates will be stored.
# @param username Name of user on portal.1c.ru.
# @param password Password of user on portal.1c.ru.
# @param tmp_folder Path to temporary folder. If None (by default),
#  it will be created automatically.
def download_and_extract_update(configuration_update_entry, store_location,
                                username, password, tmp_folder=None):
    l = LogFunc(message="Downloading file from downloads.1c.ru",
                configuration_update_entry=configuration_update_entry,
                store_location=store_location)
    # create tmp-folder, if it not exist
    if tmp_folder is None:
        tmp_folder = tempfile.mkdtemp()
    elif not os.path.exists(tmp_folder):
        os.makedirs(tmp_folder)
    # create destination location
    if configuration_update_entry["templatePath"] != None:
        template_path = pathlib.PurePath(
            configuration_update_entry["templatePath"].replace("\\", "/")
        )
        dst = os.path.join(store_location, str(template_path))
    else:
        dst = store_location
    if not os.path.exists(dst):
        os.makedirs(dst)
    # make temp filename
    temp_filename = str(uuid.uuid4()) + "." \
                    + configuration_update_entry["updateFileFormat"]
    # get file from URL
    url = configuration_update_entry["updateFileUrl"]
    response = requests.get(
        url, stream=True, auth=(username, password),
        headers={
            "User-Agent": "1C+Enterprise/8.3",
        }
    )
    global_logger.debug(message="Download file response",
                        http_code=response.status_code,
                        headers=response.headers)
    temp_file = os.path.join(tmp_folder, temp_filename)
    with open(temp_file, "wb") as f:
        shutil.copyfileobj(response.raw, f)
    # try to unpack, if necessary
    if configuration_update_entry["updateFileFormat"].lower() == "zip":
        unpack_zip(temp_file, dst, "cp866")
    elif splitext_archive(temp_file)[1] \
         in KNOWN_ARCHIVE_EXTENSIONS:
        unpack_archive(temp_file, dst)
    else:
        shutil.copy(temp_file, dst)
    # check hash. If error occurred (file not found or hashes doesn't match),
    # log warning and proceed
    try:
        # build file path
        update_file = os.path.join(dst,
                                   configuration_update_entry["updateFileName"])
        if not os.path.exists(update_file):
            raise Exception
        # calculate actual hash
        hash_md5 = hashlib.md5()
        with open(update_file, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        actual_hash = hash_md5.hexdigest()
        # convert hashSum to string representation of number in base 16
        remote_hash = format(int.from_bytes(
            base64.b64decode(configuration_update_entry["hashSum"]),
            byteorder="big",
            signed=False
        ), "x")
        if actual_hash != remote_hash:
            global_logger.warning(
                message="Actual hash of .cfu file doesn't match the one "
                "returned by update-api"
            )
    except:
        global_logger.warning(message="Can't find .cfu file, proceeding without"
                              " hash checking")


class DownloadFromUpdateApiScenario:
    ## Constructor.
    # @param self Pointer to object.
    # @param config lib::common::config::Configuration object.
    # @param kwargs additional named args for config object.
    def __init__(self, config, **kwargs):
        l = LogFunc(message="initializing DownloadFromUpdateApiScenario object")
        # creating Configurations
        self.config = config
        # set global test mode variable
        gv.TEST_MODE = self.config["test-mode"]
        # validate configuration
        self.validate_config()
        # set global CONFIG variable
        gv.CONFIG = self.config
        # log self.configuration
        global_logger.debug("Scenario data: " + str(self.config))


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
            ["configuration-name", str],
            ["current-version", str],
            ["download-folder", StrPathExpanded],
            ["tmp-folder", StrPathExpanded],
            ["username", str],
            ["password", str],
            ["additional-parameters", dict],
        ]
        self.config.validate(validate_data)

    ## Execute scenario.
    # @param self Pointer to object.
    def execute(self):
        l = LogFunc(message="Downloading configuration update from update-api",
                    config_name=self.config["configuration-name"],
                    current_version=self.config["current-version"],
                    dst=self.config["download-folder"])
        # Info request, which should return list of updates (at least one),
        # otherwise consider it as error
        info_response = info_request(
            self.config["configuration-name"],
            self.config["current-version"],
            self.config["additional-parameters"]
        )
        # get links to files
        files_response = get_files_request(
            info_response,
            self.config["username"], self.config["password"],
            self.config["additional-parameters"]
        )
        # download each file
        for entry in files_response.json()["configurationUpdateDataList"]:
            download_and_extract_update(
                entry, self.config["download-folder"],
                self.config["username"], self.config["password"],
                tmp_folder=self.config["tmp-folder"]
            )


## Wrapper for scenario execution.
# @return Last error code (0 if no errors occurred).
def download_from_update_api_scenario():
    res = 1
    # execute scenario
    try:
        data = read_yaml(sys.argv[1])
        config = ScenarioConfiguration(data)
        cmd_args = bootstrap.parse_cmd_args(sys.argv[2:])
        config.add_cmd_args(cmd_args[1], True)
        bootstrap.set_debug_values(cmd_args[1])
        scenario = DownloadFromUpdateApiScenario(config)
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
    bootstrap.main(download_from_update_api_scenario,
                   os.path.basename(__file__)[0:-3])
