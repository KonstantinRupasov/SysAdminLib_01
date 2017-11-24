# coding: utf-8

import re
import os
import pathlib
import sys
import yaml
import types
from pathlib import Path
from functools import reduce


from ..utils.cvt import str_to_bool
from ..utils import *
from .errors import *
from .logger import *


## Check, is object a function or built-in function.
# @param f Object.
# @return True, if function, False otherwise.
def is_function(f):
    return isinstance(f, types.FunctionType) \
        or isinstance(f, types.BuiltinFunctionType)


## Return function, which creates list with specific type of elements.
# @param element_type Type of elements in list.
# @return Function, which creates list with specific type of elements.
def create_typed_list_builder(element_type):
    f = lambda iterable: [element_type(i) for i in iterable]
    f.__name__ = "TypedList<{}>".format(element_type.__name__)
    return f


## Return function, which check, is all elements in list is instances
#  of specific type.
# @param element_type Type of elements in list.
# @return Function, which check, is all elements in list is instances
#  of specific type.
def create_typed_list_checker(element_type):
    return lambda list: reduce(lambda acc, x: type(x) == element_type and acc,
                               list, True)


## Return pair of functions for working on typed lists.
# @param element_type Type of elements in list.
# @return Pair of functions for working on typed lists.
def create_typed_list_functions(element_type):
    return create_typed_list_builder(element_type), \
        create_typed_list_checker(element_type)


def get_value_by_path(dictionary, key_path):
    temp_var = dictionary
    keys = key_path.strip("/ ").split("/") if isinstance(key_path, str) \
           else key_path
    processed_keys = []
    try:
        for key in keys[:-1]:
            processed_keys.append(key)
            temp_var = temp_var[key]
        return temp_var[keys[-1]]
    except KeyError:
        raise KeyError("/".join(processed_keys))
    except TypeError as err:
        raise TypeError("{}: {}".format("/".join(processed_keys), str(err)))


def set_value_by_path(dictionary, key_path, value):
    temp_var = dictionary
    keys = key_path.strip("/ ").split("/") if isinstance(key_path, str) \
           else key_path
    for key in keys[:-1]:
        if key not in temp_var:
            temp_var[key] = dict()
        temp_var = temp_var[key]
    temp_var[keys[-1]] = value


def check_contains_by_path(dictionary, key_path):
    temp_var = dictionary
    keys = key_path.strip("/ ").split("/") if isinstance(key_path, str) \
           else key_path
    try:
        for key in keys[:-1]:
            if key not in temp_var:
                return False
            temp_var = temp_var[key]
        return keys[-1] in temp_var
    except:
        return False


## Subclass for strings, which expand filesystem paths.
class StrPathExpanded(str):
    def __new__(cls, content):
        var = os.path.expandvars(os.path.expanduser(content))
        return super().__new__(cls, var)


class Placeholder:

    placeholder_regex = "<(?:([a-z]+):)?([^>\\0:]+)>"

    def __init__(self, string):
        if not isinstance(string, str):
            raise TypeError("argument must be string")
        match = re.match(Placeholder.placeholder_regex, string)
        if match is None:
            raise ValueError(
                "'{}' doesn't contain correct placeholder".format(string)
            )
        # denote types, which can be set in placeholder
        types = {
            "int": int,
            "str": str,
            "float": float,
            "bool": bool,
            "path": StrPathExpanded,
        }
        groups = list(match.groups())
        if groups[0] != None and not groups[0] in types:
            raise TypeError(
                "'{}' is not valid type for placeholder".format(groups[0])
            )
        # by default, type is str
        elif groups[0] == None:
            groups[0] = "str"
        # set values
        self.__key = groups[1].strip("/ \n\r\t")
        self.__type = types[groups[0]]
        self.__str_type = groups[0]

    @property
    def key(self):
        return self.__key

    @property
    def type(self):
        return self.__type

    def __str__(self):
        return "<{}:{}>".format(self.__str_type, self.key)

    def __repr__(self):
        return "Placeholder({})".format(str(self))

    def __eq__(self, other):
        return self.key == other.key and self.type == other.type


def iter_leaves(data): # -> (object, key, value)
    iterable = None
    if isinstance(data, dict):
        iterable = data.items()
    elif isinstance(data, list):
        iterable = zip(range(0, len(data)), data)
    else:
        raise TypeError("argument must be dict or list")
    for key, value in iterable:
        if not isinstance(value, dict) and not isinstance(value, list):
            yield data, key, value
        else:
            yield from iter_leaves(value)


def replace_with_placeholders(data):
    data = data.copy()
    if not isinstance(data, dict) and not isinstance(data, list):
        raise TypeError("argument must be dict or list")
    for obj,key,value in iter_leaves(data):
        if isinstance(value, str):
            try:
                obj[key] = Placeholder(value)
            except ValueError:
                pass
    return data


def update_data_with_placeholders(src, dst):
    # if src and dst is the SAME object, copy src to dst
    if dst is src:
        dst = src.copy()
    dst = replace_with_placeholders(dst)
    while True:
        nested_placeholders_found = False
        for obj,key,value in iter_leaves(dst):
            if isinstance(value, Placeholder):
                # this try block necessary because we allow to dangle
                # Placeholder objects
                try:
                    src_value = get_value_by_path(src, value.key)
                except:
                    continue
                # try to convert new value to Placeholder
                try:
                    obj[key] = Placeholder(value.type(src_value))
                    nested_placeholders_found = True
                # if failed, just set new value
                except:
                    obj[key] = value.type(src_value)
        if not nested_placeholders_found:
            return dst


class ConfigValueType:
    def __init__(self, key_path, type_checker, type_builder=None,
                 valid_values=None, default_allowed=False, default_value=None):
        self.key_path = key_path
        self.keys = key_path.split("/")
        self.type_checker = type_checker
        # if type_builder not provided, assume that type_checker can also act as
        # builder
        self.type_builder = type_builder if type_builder else type_checker
        self.defalut_allowed = False
        self.default_value = self.type_builder(default_value) if default_value \
                             else None
        self.valid_values = valid_values

    ## Compare type with type_checker and valid_values.
    def validate(self, value):
        correct_type = self.type_checker(value) if \
                       is_function(self.type_checker) else \
                       isinstance(value, self.type_checker)
        if self.valid_values:
            if is_function(self.valid_values):
                return correct_type, self.valid_values(value)
            else:
                return correct_type, value in self.valid_values
        else:
            return correct_type, True

    ## Try to convert value via type_builder. If fails, return value.
    def try_convert(self, value):
        # TODO: change error to AutomationLibraryError
        try:
            return self.type_builder(value)
        except:
            return value

    @property
    def get_default(self):
        if not self.default_allowed:
            raise RuntimeError(
                "Default value not allowed for key '{}'".format(self.key_path)
            )
        return self.default_value


class ScenarioConfiguration:
    def __init__(self, yaml_data):
        self.raw_data = yaml_data.copy()
        self.version = PlatformVersion(self.raw_data["version"])
        # contain list of keys, which should be passed from outside
        self.external_keys = self.raw_data["external-values"]
        # contain data, which is context for this scenario and other
        # scenarios execution
        self.scenario_context = replace_with_placeholders(
            self.raw_data["default-values"]
        )
        # if "scenario" block presented, then assume that this config is
        # for composite scenario
        if "scenario" in self.raw_data \
           and isinstance(self.raw_data["scenario"], list):
            self.composite = True
            self.composite_scenario_data = replace_with_placeholders(
                self.raw_data["scenario"]
            )
            # make sure that all steps have proper type (dict or str)
            for step in self.composite_scenario_data:
                name = step["name"]
                if "command" not in step and "command-string" in step:
                    pass
                    # global_logger.warning(
                    #     message="composite scenario step is set as string, "
                    #     "which is discouraged. It will be launched as-is",
                    #     step_name=name
                    # )
                elif "command" not in step and "command-string" not in step:
                    raise AutomationLibraryError(
                        "ARGS_ERROR", "composite scenario step have invalid "
                        "type", step_name=name
                    )
        else:
            self.composite = False
            self.composite_scenario_data = None
        # if rollback-scenario presented, set it, otherwise set None
        if "rollback-scenario" in self.raw_data:
            self.rollback_scenario = self.raw_data["rollback-scenario"]
            if isinstance(self.rollback_scenario, str):
                pass
                # global_logger.warning(
                #     message="rollback-scenario is set as string, which is "
                #     "discouraged. In case if rollback will be needed, it will "
                #     "be launched as-is",rollback_scenario=self.rollback_scenario
                # )
            elif not isinstance(self.rollback_scenario, dict):
                raise AutomationLibraryError(
                    "ARGS_ERROR", "rollback-scenario have invalid type"
                )
            elif "command" not in self.rollback_scenario:
                raise AutomationLibraryError(
                    "ARGS_ERROR", "rollback-scenario set as dictionary, "
                    "but doesn't have 'command' value"
                )
            else:
                self.rollback_scenario = replace_with_placeholders(
                    self.rollback_scenario
                )
        else:
            self.rollback_scenario = None
        self.scenario_context["os-type"] = detect_actual_os_type()
        self.scenario_context["arch"] = 64 if is_64bit_arch() else 32


    def update_inner_data(self):
        # first: update scenario_context itself
        self.scenario_context = update_data_with_placeholders(
            self.scenario_context, self.scenario_context
        )
        # second: update rollback-scenario, if presented
        if isinstance(self.rollback_scenario, dict):
            self.rollback_scenario = update_data_with_placeholders(
                self.scenario_context, self.rollback_scenario
            )
        # third: update composite scenario data
        if isinstance(self.composite_scenario_data, list):
            self.composite_scenario_data = update_data_with_placeholders(
                self.scenario_context, self.composite_scenario_data
            )

    def __getitem__(self, key):
        item = get_value_by_path(self.scenario_context, key)
        if isinstance(item, Placeholder):
            return str(item)
        return item

    def __setitem__(self, key, value):
        set_value_by_path(self.scenario_context, key, value)
        self.update_inner_data()

    def __contains__(self, key):
        return check_contains_by_path(self.scenario_context, key)

    def add_cmd_args(self, cmd_args, check_completeness=False):
        if check_completeness:
            for ext_key in self.external_keys:
                if ext_key not in cmd_args.keys():
                    raise AutomationLibraryError("OPTION_NOT_FOUND",
                                                 key=ext_key)
        for key, value in cmd_args.items():
            self[key] = value
        self.update_inner_data()

    def __repr__(self):
        return "Scenario context: {}\nRollback scenario: {}\nComposite scenario: {}\n" \
            .format(self.scenario_context, self.rollback_scenario,
                    self.composite_scenario_data)

    def __str__(self):
        return "Configuration: {}".format(self.scenario_context)

    def validate(self, validate_data):
        # for each row in validate_data perform check
        for row in validate_data:
            # first build ConfigValueType
            obj = ConfigValueType(*row)
            try:
                result = obj.validate(self[obj.key_path])
            # if KeyError, raise an error
            except KeyError:
                raise AutomationLibraryError("OPTION_NOT_FOUND",
                                             key=obj.key_path)
            # if first value of result is False (ie incorrect type), try to
            # convert value and perform check again
            if result[0] == False:
                self[obj.key_path] = obj.try_convert(self[obj.key_path])
            result = obj.validate(self[obj.key_path])
            # if first value of result is False (ie incorrect type), then
            # raise ARGS_ERROR with about incorrect type
            if result[0] == False:
                raise AutomationLibraryError(
                    "ARGS_ERROR",
                    "argument have incorrect type",
                    key=obj.key_path,
                    current_type=type(self[obj.key_path]).__name__,
                    expected_type=obj.type_checker.__name__
                )
            # if second value of result is False (ie incorrect value), raise
            # error with "incorrect value". Since valid values can be
            # checked with function, add them to error message only if it is
            # not function. If it is function, all notices about valid values
            # should be printed inside that function.
            if result[1] == False:
                if is_function(obj.valid_values):
                    raise AutomationLibraryError(
                        "ARGS_ERROR", "argument have incorrect value",
                        key=obj.key_path, current_value=self[obj.key_path]
                    )
                else:
                    raise AutomationLibraryError(
                        "ARGS_ERROR", "argument have incorrect value",
                        key=obj.key_path, current_value=self[obj.key_path],
                        valid_values=obj.valid_values
                    )
