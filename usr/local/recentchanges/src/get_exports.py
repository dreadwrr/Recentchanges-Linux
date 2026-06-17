#!/usr/bin/env python3
import tomllib
import os
import shlex
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.configfunctions import find_install
from src.configfunctions import get_config
from src.gpgcrypto import GPGStatus
from src.gpgcrypto import start_user_agent
from src.gpgkeymanagement import iskey
from src.logs import check_log_perms


def get_exports():
    if len(sys.argv) < 2:
        print("Usage: get_exports.py <username>", file=sys.stderr)
        return 1
    user = sys.argv[1]

    appdata_local = find_install()  # software install aka workdir

    toml_file, json_file, home_dir, xdg_config, xdg_runtime, user, uid, gid = get_config(appdata_local, user, platform="Linux")

    log_dir = home_dir / ".local" / "state" / "recentchanges" / "logs"

    with open(toml_file, "rb") as f:
        config = tomllib.load(f)

    if user != "root":
        user_log = config.get("logs", {}).get("userLOG")
        log_path = log_dir / user_log
        check_log_perms(log_path, log_dir)

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

    home_dir = os.path.join(home_dir, ".local", "share", "recentchanges")

    export_a = {
        "home_dir": home_dir,
        "tomlf": str(toml_file),
        "CMD_LINE": "1",
        "LAUNCHED_NON_ROOT": user,
        "XDG_CONFIG_HOME": xdg_config,
        "XDG_RUNTIME_DIR": xdg_runtime
    }
    for name, value in export_a.items():
        if value is not None:
            print(f"export {name}={shlex.quote(str(value))}")

    # Warm the user gpg agent for root
    email = config['backend']['email']
    is_key = iskey(email)
    if is_key:

        pst_data = Path(home_dir) / ".local" / "share" / "save-changesnew"
        cache_f_frm = pst_data / "ctimecache.gpg"
        dbtarget = pst_data / "recent.gpg"

        cache_f = None
        if cache_f_frm.is_file():
            cache_f = str(cache_f_frm)
        elif dbtarget.is_file():
            cache_f = str(dbtarget)

        res = start_user_agent(user, email, cache_f, str(toml_file))  # pass the config as a temp file as input
        if res != GPGStatus.ERR_OK:
            if res == GPGStatus.DECRYPT_FAIL:
                sys.exit(2)
            elif res == GPGStatus.NO_KEY:
                sys.exit(3)
            elif res == GPGStatus.NO_PINENTRY:
                # or inappropriate ioctl for device
                sys.exit(4)
            elif res == GPGStatus.BAD_PASSPHRASE:
                sys.exit(7)
            else:
                sys.exit(res)


if __name__ == "__main__":
    sys.exit(get_exports())

# Notes and drafting:
# using an app specific gpupg home cluttered the folder and proved to be more difficult than just using the users homedir
# gnupg_home = appdata_local / "gnupg"
# print(f'export GNUPGHOME={shlex.quote(str(gnupg_home))}')
