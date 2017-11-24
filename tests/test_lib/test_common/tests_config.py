import unittest
import sys
import os
import yaml

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                             "..", "..", "src"))


from lib.common.config import *

global_logger.disable()


class TestKeyPath(unittest.TestCase):
    def setUp(self):
        self.data = {
            "a": 1,
            "b": {
                "c": 2,
                "d": {
                    "e": 3
                }
            },
            "b1": {
                "c": 4,
                "d": {
                    "e": 5
                }
            }
        }

    def test_get_value_by_path(self):
        # successful tests
        self.assertEqual(get_value_by_path(self.data, "a"), 1)
        self.assertEqual(get_value_by_path(self.data, "/ a/ "), 1)
        self.assertEqual(get_value_by_path(self.data, "b/c"), 2)
        self.assertEqual(get_value_by_path(self.data, "b/d"), {"e": 3})
        self.assertEqual(get_value_by_path(self.data, "/ / b/c/ / /"), 2)
        self.assertEqual(get_value_by_path(self.data, "b/d/e"), 3)
        self.assertEqual(get_value_by_path(self.data, "b1/d/e"), 5)
        # fail tests
        with self.assertRaises(KeyError, msg="c"):
            get_value_by_path(self.data, "c")
        with self.assertRaises(KeyError, msg="b/a"):
            get_value_by_path(self.data, "b/a")
        with self.assertRaises(TypeError, msg="a/b: 'int' object is not subscriptable"):
            get_value_by_path(self.data, "a/b/c")

    def test_set_value_by_path(self):
        data = {}
        set_value_by_path(data, "a", 1)
        set_value_by_path(data, "b/c", 2)
        set_value_by_path(data, "d", {"e": {"f": 3}})
        self.assertEqual(data["a"], 1)
        self.assertEqual(data["b"]["c"], 2)
        self.assertEqual(data["d"]["e"]["f"], 3)

    def test_check_contains_by_path(self):
        self.assertEqual(check_contains_by_path(self.data, "a"), True)
        self.assertEqual(check_contains_by_path(self.data, "b/c"), True)
        self.assertEqual(check_contains_by_path(self.data, "b/c/d"), False)


class TestPlaceholder(unittest.TestCase):
    def test_init(self):
        # successful tests
        self.assertEqual(str(Placeholder("<test>")), "<str:test>")
        self.assertEqual(str(Placeholder("< /test/ >")), "<str:test>")
        self.assertEqual(str(Placeholder("<test/test1>")), "<str:test/test1>")
        self.assertEqual(str(Placeholder("<str:test>")), "<str:test>")
        self.assertEqual(str(Placeholder("<int:test>")), "<int:test>")
        # fail tests
        with self.assertRaises(ValueError, msg="'<>' doesn't contain correct placeholder"):
            Placeholder("<>")
        with self.assertRaises(ValueError, msg="'<str:test' doesn't contain correct placeholder"):
            Placeholder("<str:test")
        with self.assertRaises(ValueError, msg="'<str:>' doesn't contain correct placeholder"):
            Placeholder("<str:>")
        with self.assertRaises(TypeError, msg="'none' is not valid type for placeholder"):
            Placeholder("<none:test>")

    def test_key_and_type(self):
        p = Placeholder("</    test  / / /  />")
        self.assertEqual(p.key, "test")
        self.assertEqual(p.type, str)

    def test_replace_with_placeholders(self):
        ddata = {
            "a": "<test>", "b": 3, "c": {
                "d": "<int:test/1>", "e": {
                    "f": "<int:test/2>",
                    "g": ["a", 1, "<list_test>", [1, "<list_test/1>", "2"]]
                }
            }
        }
        e_ddata = {
            "a": Placeholder("<test>"), "b": 3, "c": {
                "d": Placeholder("<int:test/1>"), "e": {
                    "f": Placeholder("<int:test/2>"),
                    "g": ["a", 1, Placeholder("<list_test>"),
                          [1, Placeholder("<list_test/1>"), "2"]]
                }
            }
        }
        self.assertEqual(replace_with_placeholders(ddata), e_ddata)
        ldata = [
            "<test>", 1, 2, ddata, ["<int:test/1>"],
        ]
        e_ldata = [
            Placeholder("<test>"), 1, 2, e_ddata, [Placeholder("<int:test/1>")],
        ]
        self.assertEqual(replace_with_placeholders(ldata), e_ldata)

    def test_update_data_with_placeholders(self):
        src = {
            "a": 1, "b": "<a>", "c": {
                "c-1": 3, "c-2": "4"
            }
        }
        src_backup = src.copy()
        src_e = {
            "a": 1, "b": "1", "c": {
                "c-1": 3, "c-2": "4"
            }
        }
        dst = replace_with_placeholders({
            "a": 1, "b": "<b>", "c": {
                "c-1": "<int:c/c-1>", "c-2": "<c/c-2>",
                "c-3": ["<a>", "<int:a>", "<b>"]
            }
        })
        e = {
            "a": 1, "b": "1", "c": {
                "c-1": 3, "c-2": "4",
                "c-3": ["1", 1, "1"]
            }
        }
        self.assertEqual(update_data_with_placeholders(src, dst), e)
        # test on same data
        self.assertEqual(update_data_with_placeholders(src, src), src_e)
        # make sure that input data is not touched
        self.assertEqual(src, src_backup)


class TestScenarioConfiguration(unittest.TestCase):
    configs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "test_data")
    def setUp(self):
        f = open(os.path.join(TestScenarioConfiguration.configs_path,
                              "test_scenario_configuration.yaml"))
        self.yaml_data = yaml.load(f)
        f.close()

    def test_init(self):
        sc = ScenarioConfiguration(self.yaml_data)
        # delete os-type, cuz it could vary from system to system
        del sc.scenario_context["os-type"]
        del sc.scenario_context["arch"]
        self.assertEqual(sc.scenario_context, {
            "test-mode": False, "clstr-login": Placeholder("<usr>"),
            "clstr-pwd": Placeholder("<pwd>"), "cf-name": "/1cv8.cf",
            "platform-version": "8.3.10.2466",
        })
        self.assertEqual(sc.rollback_scenario, {
            "command": "restore-db", "srvr": Placeholder("<srvr>"),
            "ib": Placeholder("<ib>")
        })
        self.assertEqual(sc.composite_scenario_data[0], {
            "command": "prepare-for-update",
            "name": "prepare-for-update",
            "srvr": Placeholder("<srvr>"),
            "ib": Placeholder("<ib>"),
            "clstr-login": Placeholder("<clstr-login>"),
            "clstr-pwd": Placeholder("<clstr-pwd>"),
            "usr": Placeholder("<usr>"),
            "pwd": Placeholder("<pwd>"),
            "time-limit": Placeholder("<time-limit>")
        })
        self.assertEqual(sc.composite_scenario_data[2], {
            "name": "update-db-cfg",
            "command-string": "execute_epf /UpdateDB.epf"
        })
        self.assertEqual(sc.composite, True)

    def test_init_with_str_rollback(self):
        f = open(os.path.join(
            TestScenarioConfiguration.configs_path,
            "test_scenario_configuration_with_str_rollback.yaml"
        ))
        data = yaml.load(f)
        f.close()
        sc = ScenarioConfiguration(data)
        self.assertEqual(sc.rollback_scenario,
                         "restore-db --srvr=srvr-1-1 --ib=ib-1")

    def test_init_without_composite(self):
        f = open(os.path.join(
            TestScenarioConfiguration.configs_path,
            "test_scenario_configuration_without_composite.yaml"
        ))
        data = yaml.load(f)
        f.close()
        sc = ScenarioConfiguration(data)
        self.assertEqual(sc.composite_scenario_data, None)
        self.assertFalse(sc.composite)

    def test_init_without_rollback(self):
        f = open(os.path.join(
            TestScenarioConfiguration.configs_path,
            "test_scenario_configuration_without_rollback.yaml"
        ))
        data = yaml.load(f)
        f.close()
        sc = ScenarioConfiguration(data)
        self.assertEqual(sc.rollback_scenario, None)

    def test_init_with_incorrect_rollback(self):
        data = self.yaml_data.copy()
        del data["rollback-scenario"]["command"]
        with self.assertRaises(AutomationLibraryError):
            sc = ScenarioConfiguration(data)

    def test_update_inner_data(self):
        sc = ScenarioConfiguration(self.yaml_data)
        sc.update_inner_data()
        self.assertEqual(sc.composite_scenario_data[0]["clstr-login"],
                         Placeholder("<usr>"))

    def test_scenario_context_access_shortcuts(self):
        sc = ScenarioConfiguration(self.yaml_data)
        self.assertEqual(sc["test-mode"], False)
        # check that __getitem__ convert Placeholder to string
        self.assertEqual(sc["clstr-login"], "<str:usr>")
        self.assertEqual(sc.scenario_context["clstr-login"],
                         Placeholder("<usr>"))
        # check that __setitem__ updates Placeholders
        sc["usr"] = "USER"
        self.assertEqual(sc["clstr-login"], "USER")
        self.assertEqual(sc.composite_scenario_data[0]["clstr-login"], "USER")
        # test __contains__
        self.assertTrue("clstr-login" in sc)
        self.assertFalse("there-is-no-such-key" in sc)

    def test_add_cmd_args(self):
        cmd_args = {
            "usr": "USER",
            "pwd": "PASSWORD",
            "new-version": "1.0.0.2",
        }
        sc = ScenarioConfiguration(self.yaml_data)
        with self.assertRaises(AutomationLibraryError):
            sc.add_cmd_args(cmd_args, True)
        sc.add_cmd_args(cmd_args)
        self.assertEqual(sc["clstr-login"], "USER")
        self.assertEqual(sc.composite_scenario_data[0]["clstr-login"], "USER")
        self.assertEqual(sc["clstr-pwd"], "PASSWORD")
        self.assertEqual(sc.composite_scenario_data[0]["clstr-pwd"], "PASSWORD")
        self.assertEqual(sc["new-version"], "1.0.0.2")

    def test_validate(self):
        validate_data = [
            ["test-mode", bool],
            ["cf-name", StrPathExpanded],
        ]
        sc = ScenarioConfiguration(self.yaml_data)
        sc.validate(validate_data)
        validate_data.append(["srvr", str])
        with self.assertRaises(AutomationLibraryError):
            sc.validate(validate_data)


if __name__ == '__main__':
    unittest.main()
