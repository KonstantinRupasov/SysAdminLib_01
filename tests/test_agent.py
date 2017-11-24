import unittest
import sys
import os
import yaml
import time

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_PATH, "..", "src"))


from agent import *

DICTIONARY_PATH = os.path.join(sys.path[0], "test_data", "dictionary.yaml")
TEST_DATA = os.path.join(sys.path[0], "test_data")

global_logger.disable()


class TestDictionaryEntry(unittest.TestCase):
    def test_init(self):
        obj = DictionaryEntry("script.py", "config.yaml",
                              script_prefix="test_data",
                              config_prefix="test_data")
        self.assertEqual(obj.script, "test_data/script.py")
        self.assertEqual(obj.config, "test_data/config.yaml")
        obj = DictionaryEntry("script.py", "config.yaml", "0.0.0.0", "1.0.0.0",
                              script_prefix="test_data",
                              config_prefix="test_data")
        self.assertEqual(obj.first_version, "0.0.0.0")
        self.assertEqual(obj.last_version, "1.0.0.0")
        with self.assertRaises(AutomationLibraryError) as cm_err:
            obj = DictionaryEntry("script.py", "config.yaml")
        self.assertEqual(cm_err.exception.num_code,
                         AutomationLibraryError("FILE_NOT_EXIST").num_code)

    def test_from_dict(self):
        data = {
            "config-name": "config.yaml",
            "exclude-versions": ["0.0.0.2", "0.0.0.9"],
            "first-version": "0.0.0.0",
            "last-version": "1.0.0.0",
            "script-name": "script.py"
        }
        with self.assertRaises(AutomationLibraryError) as cm_err:
            obj = DictionaryEntry.from_dict(data)
        self.assertEqual(cm_err.exception.num_code,
                         AutomationLibraryError("FILE_NOT_EXIST").num_code)
        obj = DictionaryEntry.from_dict(data, "test_data", "test_data")
        self.assertEqual(obj.script, "test_data/script.py")
        self.assertEqual(obj.config, "test_data/config.yaml")
        self.assertEqual(obj.first_version, "0.0.0.0")
        self.assertEqual(obj.last_version, "1.0.0.0")
        self.assertEqual(obj.exclude_versions, [PlatformVersion("0.0.0.2"),
                                                PlatformVersion("0.0.0.9")])


class TestSimpleStep(unittest.TestCase):
    def setUp(self):
        self.dict = AgentDictionary()
        self.dict.add_data_from_file(DICTIONARY_PATH, "test_data")

    def test_init(self):
        obj = SimpleStep("simple-step", self.dict, {}, True)
        self.assertFalse(obj.config["test-mode"])
        rollback = obj.rollback_step
        self.assertFalse(rollback.rollback)
        self.assertEqual(rollback.name, "(rollback)")
        obj = SimpleStep("simple-step", self.dict, {}, False)
        self.assertTrue(isinstance(obj.rollback_step, FakeStep))

    def test_start_execute(self):
        obj = SimpleStep("simple-step", self.dict, {}, True)
        obj.start_execution()
        obj.thread.join(10)
        self.assertEqual(obj.result, 0)
        # test long step
        obj = SimpleStep("simple-step-long", self.dict, {}, True)
        obj.start_execution()
        obj.kill()
        obj.thread.join(10)
        self.assertEqual(obj.result,
                         AutomationLibraryError("TIMEOUT_ERROR").num_code)
        # test exception step
        obj = SimpleStep("simple-step-with-exception", self.dict, {}, True)
        obj.start_execution()
        obj.thread.join(10)
        self.assertEqual(obj.result, 1)

    def test_start_rollback(self):
        pass


class TestCompositeStep(unittest.TestCase):
