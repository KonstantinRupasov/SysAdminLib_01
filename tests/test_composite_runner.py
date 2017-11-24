import unittest
import sys
import os
import yaml

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_PATH, "..", "src"))


from composite_runner import *

global_logger.disable()

class TestCompositeStep(unittest.TestCase):
    def setUp(self):
        self.data_command = {
            "name": "test_step",
            "command": "test-step",
            "arg1": "value1",
            "arg2": 2,
        }
        self.data_string = {
            "name": "test_step",
            "command-string": "test-step --arg1=value1 --arg2=2",
            "arg1": "value1",
            "arg2": 2,
        }
        self.data_nothing = {
            "name": "test_step",
            "arg1": "value1",
            "arg2": 2,
        }
        self.data_both =  {
            "name": "test_step",
            "command-string": "test-step --arg1=value1 --arg2=2",
            "command": "test-step",
            "arg1": "value1",
            "arg2": 2,
        }

    def test_init_with_command(self):
        step = CompositeStep(self.data_command)
        self.assertEqual(step.type, "dict")
        self.assertEqual(step.data, self.data_command)

    def test_init_with_string(self):
        step = CompositeStep(self.data_string)
        self.assertEqual(step.type, "string")
        self.assertEqual(step.data, self.data_string)

    def test_init_without_command_and_string(self):
        with self.assertRaises(AutomationLibraryError):
            step = CompositeStep(self.data_nothing)

    def test_init_both(self):
        step = CompositeStep(self.data_both)
        self.assertEqual(step.type, "dict")
        self.assertEqual(step.data, self.data_both)

    def test_build_cmd_args_command(self):
        step = CompositeStep(self.data_command)
        validate_data = [sys.executable, os.path.join(sys.path[0], "agent.py"),
                         "test-step", "--arg1=value1", "--arg2=2",
                         "--rollback=disable"]
        self.assertCountEqual(step.build_cmd_args(), validate_data)

    def test_build_cmd_args_string(self):
        step = CompositeStep(self.data_string)
        validate_data = [sys.executable, os.path.join(sys.path[0], "agent.py"),
                         "test-step", "--arg1=value1", "--arg2=2",
                         "--rollback=disable"]
        self.assertCountEqual(step.build_cmd_args(), validate_data)

    def test_build_cmd_args_both(self):
        step = CompositeStep(self.data_both)
        validate_data = [sys.executable, os.path.join(sys.path[0], "agent.py"),
                         "test-step", "--arg1=value1", "--arg2=2",
                         "--command-string=test-step --arg1=value1 --arg2=2",
                         "--rollback=disable"]
        self.assertCountEqual(step.build_cmd_args(), validate_data)
