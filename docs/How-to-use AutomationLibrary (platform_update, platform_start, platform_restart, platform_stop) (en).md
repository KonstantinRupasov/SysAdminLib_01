# How to use `platform_update.py`, `platform_start.py`, `platform_stop.py`, `platform_restart.py`

## Requirements

- Python interpreter with version >=3.4.3;
- additional Python packages: pyyaml;
- supported web servers: Apache and IIS (Windows only);
- supported Apache versions: 2.0-2.4;
- supported IIS versions: 5.1 - 10.0;
- Linux:
  - Systemd should be presented as well as D-Bus;
  - for starting web server, its service name should be 'apache2';
- Windows:
  - Windows version XP or higher;
  - for starting web server, its service name should be 'Apache2.x', depend on Apache version.

## Preparation

Before working with program, Python dependencies should be installed (listed in `requirements.txt`; they could be installed via `pip install -r requirements.txt`).

## Usage

Script can be started with the following command:

    $ <Python interpreter> <path to script> <path to config> [<command line arguments>]

i.e., if current working directory is one level above script, and there is a configuration file in 'configs' folder, then script can be invoked like this:

    $ python3 AutomationLibrary/platform_update.py configs/platform_update.yaml --new-version=8.3.10.2466

Arguments for script (listed both in `external-values` and `default-values` in configuration file) can be passed to script via command line like `--<key>[=<value>]`. If `<value>` omitted, then it sets to Python `True` value. For setting "nested" keys (`["service-1c"]["login"]`), keys should be separated by slash, like `--service-1c/login=Username.

Arguments, listed in `external-values`, **SHOULD** be passed via command line!

## How to store distros for `platform_update.py`

Path, where stored copy of distros, sets in `distr-folder` parameter (in configuration file or command line).

Script automatically adds to this path version of platform, i.e. if `distr-folder` set to `/var/1c_distros/linux` and `new-version` set to `8.3.10.2466`, then distro will be searched in `/var/1c_distros/linux/8.3.10.2466`.

For Linux: script assume, that distro packed in .tar.gz archive, which contains all necessary packages (for DEB systems: deb.tar.gz for 32-bit systems and deb64.tar.gz for 64-bit systems; for RPM systems: rpm.tar.gz for 32-bit systems and rpm64.tar.gz for 64-bit systems).

For Windows: script assume, that distro will we presented as unpacked folder, where will be installer files (`setup.exe`, `*.msi`) or already installed copy of platform (its `bin` folder, where lie `ragent.exe`, `ras.exe`).

## Code documentation.

Code contains documentation in doxygen utility format. This documentation can be built to HTML, PDF or other formats, supported by doxygen, with Doxyfile file in root directory of code.
