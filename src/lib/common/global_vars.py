## Path to .pid file.
PID_PATH = "./"
## Is test-mode set. By default it is True, for security. It should be changed
#  ASAP, while configuration loads.
TEST_MODE = True
## global common::config::Configuration object.
CONFIG = dict({ "timeout": 100 })
## Should debug messages be printed.
DEBUG = False
## Should multi line string in log be collapsed.
COLLAPSE_TRACEBACK = True
## Global encoding variable.
ENCODING = "raw_unicode_escape"
## Should function names be printed in log records.
PRINT_FUNCTION = False
## Should operation UUID be printed in log records.
PRINT_UUID = False
## Should operation begin be printed in log records.
PRINT_BEGIN = False
## Escape key values in log records.
ESCAPE_STRINGS = False
## Langs, avaliable in platform.
LANGS = ["az", "en", "bg", "hu", "vi", "ka", "zh", "lv", "lt", "de", "pl", "ro",
         "ru", "tr", "uk", "fr"]
