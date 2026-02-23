#!/usr/bin/env python3
import tomllib
import os
import shlex
import sys
from src.logs import check_log_perms
from src.configfunctions import get_config
from src.configfunctions import find_install


def get_exports():
    if len(sys.argv) < 2:
        print("Usage: get_exports.py <username>", file=sys.stderr)
        return 1
    user = sys.argv[1]

    appdata_local = find_install()  # software install aka workdir

    toml_file, json_file, home_dir, xdg_config, xdg_runtime, user, uid, gid = get_config(appdata_local, user)

    log_dir = home_dir / ".local" / "state" / "recentchanges" / "logs"
    os.makedirs(log_dir, mode=0o755, exist_ok=True)
    with open(toml_file, "rb") as f:
        config = tomllib.load(f)

    if user != "root":
        user_log = config.get("logs", {}).get("userLOG")
        log_path = log_dir / user_log
        check_log_perms(log_path)

    # to /usr/local/bin/recentchanges
    nested_sections = {
        'email': ['backend'],
        'name': ['backend'],
        'dspEDITOR': ['display'],
        'dspPATH': ['display']
    }

    for key_name, parent_sections in nested_sections.items():
        for section in parent_sections:
            value = config.get(section, {}).get(key_name)
            if value is not None:
                val = str(value).lower() if isinstance(value, bool) else str(value)
                print(f'export {key_name}={shlex.quote(val)}')

    # all
    # flatten_sections = ['backend', 'logs', 'search', 'analytics', 'display', 'diagnostics', 'paths']
    #
    # for section in flatten_sections:
    #    section_data = config.get(section, {})
    #    for k, v in section_data.items():
    #        val = str(v).lower() if isinstance(v, bool) else str(v)
    #        print(f'export {k}={shlex.quote(val)}')

    export_a = {
        "lclhome": str(appdata_local),
        "tomlf": str(toml_file),
        "LAUNCHED_NON_ROOT": user,
        "XDG_CONFIG_HOME": xdg_config,
        "XDG_RUNTIME_DIR": xdg_runtime
    }
    for name, value in export_a.items():
        if value is not None:
            print(f"export {name}={shlex.quote(str(value))}")

    return 0


if __name__ == "__main__":
    sys.exit(get_exports())
