# coding: utf-8

import datetime as dt
import inspect
import logging
import os
import sys
import uuid
import re


from . import global_vars as gv
from .errors import AutomationLibraryError


## Class, which implement logging. It is singleton.
class Logger:
    __instance = None
    ## Underlying logging.Logger object, used as main logger object.
    __standard_logger = None
    ## Underlying logging.Logger object, used when we needs to print raw data to
    # log.
    __standard_raw_logger = None
    __tracked_operations = dict()
    __log_streams = list()
    __log_files = list()
    __fmt = "[%(levelname)s] %(asctime)s.%(msecs)03d-%(duration)s,%(message)s"
    __datefmt = "%Y-%m-%d %H:%M:%S"
    __disabled = False

    ## Implementation of Singleton concept.
    def __new__(cls, **kwargs):
        # return immediately if __instance already created, otherwise
        # initialize logger
        if Logger.__instance is None:
            Logger.__instance = object.__new__(cls)
            Logger.__standard_logger = logging.getLogger(
                "1cPlatformUpdateLogger"
            )
            Logger.__standard_logger.setLevel("DEBUG")
            # create logger object for printing raw strings
            Logger.__standard_raw_logger = logging.getLogger(
                "1cPlatformUpdateLoggerRaw"
            )
            Logger.__standard_raw_logger.setLevel("DEBUG")
        return Logger.__instance

    ## Begin of tracking operation time.
    # @param self Pointer to object.
    # @return UUID of tracking operation.
    def start_operation(self):
        operation_uuid = uuid.uuid4()
        time_stamp = dt.datetime.now()
        Logger.__tracked_operations[operation_uuid] = time_stamp
        return operation_uuid


    ## End of tracking operation time.
    # @param self Pointer to object.
    # @param operation_uuid UUID of tracking operation.
    # @return Time of operation as datetime.timedelta.
    def finish_operation(self, operation_uuid):
        delta = dt.datetime.now() - Logger.__tracked_operations[operation_uuid]
        del Logger.__tracked_operations[operation_uuid]
        return delta

    def __getattr__(self, name):
        return getattr(self.__standard_logger, name)

    ## Print raw strings.
    # @param self Pointer to object.
    # @param text Text to print.
    def print_raw_text(self, text):
        if Logger.__disabled:
            return
        self.debug(message="Multiprocessing log begin")
        Logger.__standard_raw_logger.info(
            text.strip("\r\n\ "),
        )
        self.debug(message="Multiprocessing log end")

    ## Make log string from values.
    # @param cmd_args List or tuple of values.
    # @param kwargs Dictionary of values and keys.
    # @return String with values.
    @staticmethod
    def make_log_string(cmd_args, kwargs):
        def escape_string(s):
            if gv.ESCAPE_STRINGS:
                return escape_log_string(s)
            else:
                return s

        text = "pid={},test_mode={}".format(os.getpid(),
                                            gv.TEST_MODE)
        # string all args
        args = cmd_args
        args = [escape_string(str(arg).replace("\\\\", "\\")) for arg in args]
        # join all values into one string.
        text = ",".join([text, ] + list(
            # make strings from key-value pairs of kwargs
            ["{}={}".format(
                key, escape_string(str(value).replace("\\\\", "\\"))
            ) for key, value in kwargs.items()]
        ) + args)
        # replace double backward-slashes with single backward slash
        # and strip \r and \\r
        text = text.replace("\r", "")
        text = text.replace("\\r", "")
        # text = text.replace("\\\\", "\\")
        if gv.COLLAPSE_TRACEBACK:
            return text.replace("\n", "\\n ")
        else:
            return text

    ## Log a record on INFO level.
    # @param self Pointer to object.
    # @param *args Positional arguments.
    # @param **kwargs Named arguments.
    def info(self, *args, **kwargs):
        if Logger.__disabled:
            return
        # set duration to 0 if not supplied
        if "duration" not in kwargs:
            duration = 0
        else:
            duration = kwargs["duration"]
            del kwargs["duration"]
        # calling info method of Logger.__standard_logger
        return Logger.__standard_logger.info(Logger.make_log_string(args,
                                                                    kwargs),
                                             extra={"duration": duration})

    ## Log a record on WARNING level.
    # @param self Pointer to object.
    # @param *args Positional arguments.
    # @param **kwargs Named arguments.
    def warning(self, *args, **kwargs):
        if Logger.__disabled:
            return
        if "duration" not in kwargs:
            duration = 0
        else:
            duration = kwargs["duration"]
            del kwargs["duration"]
        # calling warning method of Logger.__standard_logger
        return Logger.__standard_logger.warning(Logger.make_log_string(args,
                                                                       kwargs),
                                                extra={"duration": duration})

    ## Log a record on ERROR level.
    # @param self Pointer to object.
    # @param *args Positional arguments.
    # @param **kwargs Named arguments.
    def error(self, *args, **kwargs):
        if Logger.__disabled:
            return
        if "duration" not in kwargs:
            duration = 0
        else:
            duration = kwargs["duration"]
            del kwargs["duration"]
        # calling error method of Logger.__standard_logger
        return Logger.__standard_logger.error(Logger.make_log_string(args,
                                                                     kwargs),
                                              extra={"duration": duration})

    ## Log a record on DEBUG level.
    # @param self Pointer to object.
    # @param *args Positional arguments.
    # @param **kwargs Named arguments.
    def debug(self, *args, **kwargs):
        if Logger.__disabled:
            return
        # if global DEBUG is False, return immediately
        if not gv.DEBUG:
            return
        if "duration" not in kwargs:
            duration = 0
        else:
            duration = kwargs["duration"]
            del kwargs["duration"]
        # calling debug method of Logger.__standard_logger
        return Logger.__standard_logger.debug(Logger.make_log_string(args,
                                                                     kwargs),
                                              extra={"duration": duration})

    ## Add file handler to logger.
    # @param path Path to file.
    # @param level Minimum log level.
    # @param filter_level If True, then ONLY level records will be logged.
    def add_file_handler(self, path, level="DEBUG", filter_level=False):
        # append new stream to streams list
        if path in Logger.__log_files:
            return
        Logger.__log_files.append(path)
        # creating new handler
        stream_handler = logging.StreamHandler(open(path, "a"))
        # set formatter
        stream_handler.setFormatter(logging.Formatter(
            fmt=Logger.__fmt,
            datefmt=Logger.__datefmt,
        ))
        # set filter if necessary
        if filter_level is True:
            stream_handler.addFilter(
                lambda record, level: 1 if record.levelname == level else 0
            )
        # setting level
        stream_handler.setLevel(level)
        # add handler to __standard_logger
        Logger.__standard_logger.addHandler(stream_handler)
        # set handler for raw logger
        stream_raw_handler = logging.StreamHandler(open(path, "a"))
        stream_raw_handler.setFormatter(logging.Formatter(
            fmt="%(message)s",
            datefmt=Logger.__datefmt,
        ))
        if filter_level is True:
            stream_raw_handler.addFilter(
                lambda record, level: 1 if record.levelname == level else 0
            )
        stream_raw_handler.setLevel(level)
        Logger.__standard_raw_logger.addHandler(stream_raw_handler)

    ## Add stream handler to logger.
    # @param stream_obj Stream object.
    # @param level Minimum log level.
    # @param filter_level If True, then ONLY level records will be logged.
    def add_stream_handler(self, stream_obj, level="DEBUG", filter_level=False):
        if stream_obj in Logger.__log_streams:
            return
        Logger.__log_streams.append(stream_obj)
        stream_handler = logging.StreamHandler(Logger.__log_streams[-1])
        stream_handler.setFormatter(logging.Formatter(
            fmt=Logger.__fmt,
            datefmt=Logger.__datefmt,
        ))
        if filter_level is True:
            stream_handler.addFilter(
                lambda record, level: 1 if record.levelname == level else 0
            )
        stream_handler.setLevel(level)
        Logger.__standard_logger.addHandler(stream_handler)
        # set handler for raw logger
        stream_raw_handler = logging.StreamHandler(Logger.__log_streams[-1])
        stream_raw_handler.setFormatter(logging.Formatter(
            fmt="%(message)s",
            datefmt=Logger.__datefmt,
        ))
        if filter_level is True:
            stream_raw_handler.addFilter(
                lambda record, level: 1 if record.levelname == level else 0
            )
        stream_raw_handler.setLevel(level)
        Logger.__standard_raw_logger.addHandler(stream_raw_handler)


    ## This method return tuple (list_of_stream_objects, list_of_file_paths).
    # @param Pointer to object.
    # @return Tuple (list_of_stream_objects, list_of_file_paths).
    def get_outputs(self):
        return Logger.__log_streams, Logger.__log_files

    ## Set Logger outputs.
    # @param self Pointer to object.
    # @param log_streams List of stream objects.
    # @param log_files List of file paths.
    def set_outputs(self, log_streams=(), log_files=()):
        for stream in log_streams:
            self.add_stream_handler(stream)
        for f in log_files:
            self.add_file_handler(f)

    ## Remove all handlers from logger.
    # @param self Pointer to object.
    def remove_outputs(self):
        Logger.__standard_logger.handlers = []
        Logger.__standard_raw_logger.handlers = []

    @staticmethod
    def disable():
        Logger.__disabled = True

    @staticmethod
    def enable():
        Logger.__disabled = False


## Global logger variable
global_logger = Logger()
global_logger.add_stream_handler(sys.stdout)


## Class, which can measure time and log it on createion and destruction.
class LogFunc:

    ## Constructor.
    # @param self Pointer to object.
    # @param print_begin Enable or disable printing beginning of operation.
    #  Default value is equal to global_vars.PRINT_BEGIN.
    # @param print_uuid Enable or disable printing UUID of operation.
    #  Default value is equal to global_vars.PRINT_UUID.
    # @param print_function Enable or disable printing function name.
    #  Default value is equal to global_vars.PRINT_FUNCTION.
    def __init__(self, print_begin=None, print_uuid=None,
                 print_function=None, **kwargs):
        # setting print_* variables
        self.print_begin = print_begin if print_begin is not None \
                           else gv.PRINT_BEGIN
        self.print_uuid = print_uuid if print_uuid is not None \
                           else gv.PRINT_UUID
        self.print_function = print_function if print_function is not None \
                           else gv.PRINT_FUNCTION
        # save kwargs
        self.kwargs = kwargs
        # save operation UUID
        self.op_uuid = global_logger.start_operation()
        # if print_{uuid, function} is True, then save corresponded value to
        # kwargs
        if self.print_uuid:
            self.kwargs["uuid"] = self.op_uuid
        if self.print_function:
            self.kwargs["function"] = inspect.stack()[1][3] \
                                      if len(inspect.stack()) > 2 \
                                      else inspect.stack()[0][3]
        # if print_begin is set, record beginning of operation
        if self.print_begin:
            global_logger.info(state="begin", **self.kwargs)

    ## Destructor.
    # @param self Pointer to object.
    def __del__(self):
        time = global_logger.finish_operation(self.op_uuid)
        if self.print_begin:
            global_logger.info(
                duration=int(time.microseconds * 10**-3 + time.seconds * 10**3),
                state="end",
                **self.kwargs
            )
        else:
            global_logger.info(
                duration=int(time.microseconds * 10**-3 + time.seconds * 10**3),
                **self.kwargs
            )


def escape_log_string(string):
    translate_table = str.maketrans({
        ",": "\\,",
        "\\": "\\\\",
    })
    return string.translate(translate_table)


def unescape_log_string(string):
    result = ""
    it = range(0, len(string)).__iter__()
    for i in it:
        if string[i] != "\\":
            result += string[i]
            continue
        result += string[i+1]
        consume(it, 1)
    return result


def parse_log_record(record):
    data = {}
    data["values"] = {}
    data["record_type"], data["timestamp"], data["duration"] = re.search(
        "\\[([A-Z]+)\\] (\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}\\.\\d{1,3})-(\\d{1,})",
        record
    ).groups()[0:3]
    data["timestamp"] = dt.datetime.strptime(data["timestamp"],
                                             "%Y-%m-%d %H:%M:%S.%f")
    data["duration"] = int(data["duration"])
    for match in re.finditer("([a-zA-Z0-9_]+)=(.+?(?:(?<!\\\\),|$))",
                             record, re.S):
        groups = match.groups()
        data["values"][groups[0]] = unescape_log_string(groups[1])
    return data
