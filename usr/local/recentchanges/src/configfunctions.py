import getpass
import json
import os
import pwd
import shutil
import sys
import subprocess
import tomlkit
from pathlib import Path
# import getpass


# app location if files are moved to a src or separate directory its the one below it
def find_install():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def not_absolute(user_path: str, quiet=False) -> bool:
    p = Path(user_path)
    if p.is_absolute():
        if not quiet:
            print("proteus_EXTN path cant be absolute: ", p)
        # raise ValueError("Absolute paths not allowed")
        return False
    return True


def check_config(paths, nogo, filterout):
    for entry in paths + nogo + filterout:
        if not not_absolute(entry):
            return False
    return True


def get_user():
    """ read from environ inaccurate """
    user = None
    try:
        user = getpass.getuser()
        #  user = pwd.getpwuid(os.geteuid()).pw_name
    except (KeyError, OSError):
        print("unable to get username attempting fallback")
    if not user:
        try:
            user = Path.home().parts[-1]
        except RuntimeError as e:
            raise RuntimeError("unable to find current user.") from e
    return user


def user_info(user=None):
    try:
        if user:
            usr_info = pwd.getpwnam(user)
        else:
            usr_info = pwd.getpwuid(os.geteuid())
        USR = usr_info.pw_name
        uid = usr_info.pw_uid
        gid = usr_info.pw_gid  # gid = grp.getgrnam(user).gr_gid
        home_dir = Path(usr_info.pw_dir)

        return USR, uid, gid, home_dir
    except (KeyError, OSError) as e:
        raise ValueError(f"unable to get info for {user if user else 'current user'}") from e


def get_default_user(path="/usr/local/bin/recentchanges"):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("default_user="):
                value = line.split("=", 1)[1]
                return value.strip().strip('"')
    return None


def ensure_default_utils():
    required = ["md5sum", "find"]
    missing = [cmd for cmd in required if shutil.which(cmd) is None]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(f"Missing required utility(s): {missing_str}")

    try:
        out = subprocess.run(
            ["find", "--version"],
            capture_output=True,
            text=True,
            check=True
        ).stdout
    except Exception as e:
        raise RuntimeError(f"Unable to validate GNU find: {type(e).__name__} {e}")

    if "GNU findutils" not in out:
        raise RuntimeError("Unsupported `find` detected. GNU findutils is required.")


def get_xdg_runtime(uid):
    # uid_str = os.environ.get("PKEXEC_UID")
    # if uid_str:
    #     runtime_dir = f"/run/user/{uid_str}"
    # else:
    # raise RuntimeError("Not launched via pkexec (PKEXEC_UID missing)")
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir:
        if uid is None:
            raise RuntimeError("environment xdg_runtime_dir not set and there is uid is None")
        runtime_dir = f"/run/user/{uid}"
    xdg_runtime = Path(runtime_dir)
    if not xdg_runtime.is_dir() or (int(uid) == 0 and xdg_runtime.stat().st_uid != 0):
        xdg_runtime = Path(f"/tmp/recentchanges-{uid}")
        os.makedirs(xdg_runtime, mode=0o700, exist_ok=True)
    # print("runtime_dir", runtime_dir)
    return xdg_runtime


# toml


def get_config(appdata_local=None, user=None):
    """ user configuration location """
    config_copy = "config (copy).toml"
    json_copy = "usrprofile (copy).json"

    if appdata_local:
        default_conf = appdata_local / "config" / config_copy
        default_json = appdata_local / "config" / json_copy
    else:
        default_conf = Path(os.path.join("/usr/local/recentchanges/config/", config_copy))
        default_json = Path(os.path.join("/usr/local/recentchanges/config/", json_copy))

    user, uid, gid, home_dir = user_info(user)

    xdg_config = os.environ.get("XDG_CONFIG_HOME")

    if xdg_config:
        config_home = Path(xdg_config)

    elif home_dir:
        config_home = home_dir / ".config"
    # fallback
    else:
        if user == "root":
            default_conf_home = "/root/.config"
        else:
            default_conf_home = f"/home/{user}/.config"
        config_home = Path(default_conf_home)

    config_local = config_home / "recentchanges"

    toml_file = config_local / "config.toml"
    json_file = config_local / "usrprofile.json"

    os.makedirs(config_local, mode=0o755, exist_ok=True)
    toml_missing = not toml_file.is_file()
    json_missing = not json_file.is_file()
    first_time_setup = toml_missing and json_missing

    if toml_missing and default_conf.is_file():
        shutil.copy(default_conf, toml_file)

    if json_missing and default_json.is_file():
        shutil.copy(default_json, json_file)

    if first_time_setup:
        ensure_default_utils()

    xdg_runtime = get_xdg_runtime(uid)
    if toml_file.is_file():
        return toml_file, json_file, home_dir, xdg_config, xdg_runtime, user, uid, gid
    raise FileNotFoundError(f"Unable to find config.toml config file in {config_local}")


# def load_toml(conf_path):  #tomllib standard library. does not preserve commenting**
#     if not conf_path.is_file():
#         print("Unable to find config file:", conf_path)
#         sys.exit(1)
#     try:
#         with open(conf_path, 'rb') as f:
#             config = tomllib.load(f)
#     except Exception as e:
#         print(f"Failed to parse TOML: {e}")
#         sys.exit(1)
#     return config


def load_toml(conf_path):  # tomlkit
    conf_path = Path(conf_path)
    if not conf_path.is_file():
        print("Unable to find config file:", conf_path)
        return None
    text = conf_path.read_text(encoding="utf-8")
    try:
        config = tomlkit.parse(text)
    except Exception as e:
        print(f"Failed to parse TOML: {e}")
        return None
    return config


# from qt memory
def dump_toml(keyValuePairs, doc, filePath):
    if keyValuePairs:
        for keyName, settings in keyValuePairs.items():
            if keyName in doc:
                for settingName, newValue in settings.items():
                    if newValue is not None:
                        doc[keyName][settingName] = newValue
            else:
                print(f"Key {keyName} not found in the TOML file.")
    with open(filePath, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(doc))


def update_toml_values(keyValuePairs, filePath):
    # similar to update_toml_setting but integrated with key pairs
    try:
        with open(filePath, "r", encoding="utf-8") as f:
            doc = tomlkit.parse(f.read())
        dump_toml(keyValuePairs, doc, filePath)
        return True
    except Exception as e:
        print(f"Failed to update toml {filePath} setting. check key value pair {type(e).__name__} {e}")
        return False


def update_toml_setting(keyName, settingName, newValue, filePath):
    # update the toml to disable\enable a setting
    try:
        # config = toml.load(file_path)    removes commenting **      tomblib
        # if keyf in config and stng in config[keyf]:
        #     config[keyf][stng] = False
        #     with open(file_path, 'w') as file:
        #         toml.dump(config, file)

        with open(filePath, "r", encoding="utf-8") as f:
            doc = tomlkit.parse(f.read())

        doc[keyName][settingName] = newValue

        with open(filePath, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(doc))
    except Exception as e:
        print(f"Failed to update toml {filePath} setting. check key value pair {type(e).__name__} {e}")
        raise


# end toml


# json mem
def update_dict(updates, data, drive=None):
    if drive:  # Drive-info
        if updates is None:
            data.pop(drive, None)  # Remove entire drive listing
        else:
            if drive not in data or not isinstance(data[drive], dict):
                data[drive] = {}
            target = data[drive]
            for k, v in updates.items():
                if v is None:
                    target.pop(k, None)
                else:
                    target[k] = v
    else:
        # Top-level
        if updates is not None:
            target = data
            for k, v in updates.items():
                if v is None:
                    target.pop(k, None)
                else:
                    target[k] = v


def update_j_settings(updates, data: dict, drive=None, filepath="usrprofile.json"):
    ''' sync memory and json file '''
    update_dict(updates, data, drive)
    dump_j_settings(data, filepath)
# end json mem


def dump_j_settings(data, filepath="usrprofile.json"):
    ''' save json '''
    try:
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
    except IOError as e:
        print(f"Error writing to {filepath}: {e}")


def set_json_settings(updates=None, drive=None, filepath="usrprofile.json"):
    ''' change a setting in json file '''
    path = Path(filepath)
    if path.is_file():
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    update_j_settings(updates, data, drive, filepath)
    # path.write_text(json.dumps(data, indent=4))


def get_json_settings(keys=None, drive=None, filepath="usrprofile.json"):
    ''' load json '''
    path = Path(filepath)
    if not path.is_file():
        return {} if keys is None else {k: None for k in keys}

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {} if keys is None else {k: None for k in keys}

    target = data.get(drive, {}) if drive else data

    if keys is None:
        return target

    return {k: target.get(k) for k in keys}
