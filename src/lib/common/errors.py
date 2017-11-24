# coding: utf-8

import datetime as dt
import os
# table <num_code, str_code, decsription>
error_table = [
    (0, "OK", "OK"),
    (1, "UNKNOWN", "Unknown error,type={},value={}"),
    (2, "NOT_IMPLEMENTED", "Method not implemented"),
    (3, "UNKNOWN_ERROR_CODE",
     "Such error ({}) not presented in table or code have invalid type ({})"),
    (4, "TIMEOUT_ERROR", "Timeout expired"),
    (5, "PYTHON_INCOMPATIBLE_VERSION", "Incompatible version of Python"
     " interpreter. Minimum required: 3.4.3,value={}"),
    (6, "ARGS_ERROR", "Arguments error: {}"),
    (7, "CMD_RESULT_ERROR", "External utility returned non-successful code"),
    (8, "ROLLBACK_ERROR", "Error occurred on rollback scenario"),


    # system errors
    (10, "FILE_NOT_EXIST", "File not exist,path={}"),
    (11, "FILE_PERM_DENIED", "File: permission denied,path={}"),
    (12, "YAML_PROBLEM_MARK",
     "\"Error while parsing YAML file in position {},{}: {}\",path={}"),
    (13, "YAML_COMMON_ERROR",
     "\"Error while parsing YAML file: {}\",path={}"),
    (14, "URL_ERROR", "Error while working with URL: {}"),
    (15, "UNPACK_ERROR", "Error while unpack {}."),
    (16, "FILE_COPY_ERROR", "Error while copy file(s) from {} to {}: {}"),
    (17, "SERVICE_ERROR", "Service error: {}"),
    (18, "INSTALL_ERROR", "Installation error: {}"),
    (19, "BROWSER_ERROR", "Error while browsing site: {}"),
    (20, "NOT_JSON", "Content is not JSON document"),

    #config errors
    (30, "NO_ARCHITECTURE", "Unable to detect platform arch"),
    (31, "OPTION_NOT_FOUND", "Required option not found in configuration"),
    (32, "OS_DOESNT_MATCH", "Actual OS ({}) does not match OS in configuration ({})"),
    (33, "OLD_VERSION_DOESNT_MATCH", "Old version of 1C ({}) doesn't match"
     " version in configuration ({})"),
    (34, "OLD_VERSION_NOT_DETECTED", "Cannot find old version or cannot extract"
     " version property"),

    # Linux specific errors
    (40, "LINUX_SERVICE_NOT_FOUND", "Service {} not found"),
    (41, "LINUX_SERVICE_INVALID_STATE", "Service '{}' in invalid state '{}'"),
    (42, "LINUX_SERVICE_PERM_DENIED", "Access to service control denied"),

    # DEB specific errors
    (50, "DPKG_PERM_DENIED", "dpkg: permission denied"),
    (51, "DPKG_ERROR", "dpkg error occured"),
    (52, "DPKG_PACKAGE_ERROR", "dpkg: error occurred while dry run of package {}: {}"),

    # RPM specific errors
    (60, "RPM_PERM_DENIED", "rpm: permission denied"),
    (61, "RPM_ERROR", "rpm error occured"),
    (62, "RPM_INSTALL_FAILED", "rpm: update of package {} failed: {}"),
    (63, "RPM_PACKAGE_ERROR", "rpm: error occurred while dry run of package {}: {}"),

    # Win specific errors
    (70, "WIN_INSTALL_PERM_DENIED", "windows: install permission denied"),
    (71, "WIN_SC_ERR", "windows: service control error: {} ({})"),
    (72, "WIN_SERVICE_NOT_FOUND", "Service {} not found"),
    (73, "WIN_SERVICE_INVALID_STATE", "Service '{}' in invalid state '{}'"),
    (74, "WMIC_ERROR", "WMIC error"),
]

## Class, which represents errors, specific to Automation library
class AutomationLibraryError(Exception):

    ## Constructor
    #
    # @param self Pointer to object.
    # @param code Number or string code of error from
    #  lib::common::errors::error_table.
    # @param args Positional args, which will be added to format of error message.
    # @param kwargs Named arguments, which will be added to string representation.
    def __init__(self, code, *args, **kwargs):
        super().__init__()

        self.duration = kwargs["duration"] if "duration" in kwargs else \
            dt.timedelta()
        # get message and alternative representation of error code
        if type(code) in [int, str]:
            for row in error_table:
                if code in row:
                    self.num_code = row[0]
                    self.str_code = row[1]
                    self.description = row[2]
                    break
        # if num_code not set (ie code was not found in table), raise
        # UNKNOWN_ERROR_CODE
        if not hasattr(self, "num_code"):
            raise AutomationLibraryError("UNKNOWN_ERROR_CODE", code, type(code))

        # save args
        self.args = args
        # if code is UNKNOWN, then add type of error to self.args
        if self.str_code == "UNKNOWN":
            self.__traceback__ = self.args[0].__traceback__
            self.args = tuple([type(self.args[0]), ] + list(self.args))
        # save kwargs
        self.kwargs = kwargs

    ## Return string representation of object.
    #
    # @param self Pointer to object.
    def __str__(self):
        import traceback
        import io
        tb_str = io.StringIO()
        traceback.print_tb(self.__traceback__, file=tb_str)
        lst = ["code={}".format(self.num_code),
               "str_code={}".format(self.str_code),
               "message={}".format(self.description.format(*self.args))]
        lst += ["{}={}".format(k, v) for k, v in self.kwargs.items()]
        if "traceback" not in self.kwargs:
            lst += ["traceback={}".format(tb_str.getvalue()), ]
        return ",".join(lst)

    def serialize(self):
        import traceback
        import io
        tb_str = io.StringIO()
        traceback.print_tb(self.__traceback__, file=tb_str)
        self.kwargs["traceback"] = tb_str.getvalue()
        return ["AutomationLibrary", self.num_code, self.str_code, self.args,
                self.kwargs]

    @staticmethod
    def deserialize(data):
        return AutomationLibraryError(data[2], *data[3], **data[4])
