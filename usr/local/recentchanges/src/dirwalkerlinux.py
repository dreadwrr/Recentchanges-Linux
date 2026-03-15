import grp
import pwd
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from .config import load_toml
from .configfunctions import get_config
from .logs import emit_log
from .pyfunctions import epoch_to_date
from .pyfunctions import epoch_to_str
from .pyfunctions import user_path


@dataclass
class ConfigData:
    home_dir: Path
    xdg_runtime: Path
    toml_file: Path
    json_file: Path
    log_file: Path
    uid: int
    gid: int
    config: Dict
    EXCLDIRS: list
    nogo: list
    filterout_list: list
    driveTYPE: str
    ll_level: str


# read the config for dirwalker to avoid passing too many arguments
# return configs files toml, json and log file
# if the user is root return a root log file to avoid permission errors if user switches back to user
def get_config_data(appdata_local, USR):

    toml_file, json_file, home_dir, _, xdg_runtime, USR, uid, gid = get_config(appdata_local, USR, platform="Linux")  # xdg_config

    config = load_toml(toml_file)
    if not config:
        sys.exit(1)
    EXCLDIRS = user_path(config['search']['EXCLDIRS'], USR)
    nogo = user_path(config['shield']['nogo'], USR)
    filterout_list = user_path(config['shield']['filterout'], USR)
    driveTYPE = config['search']['driveTYPE']
    ll_level = config['logs']['logLEVEL']
    root_log_file = config['logs']['rootLOG']
    log_file = config['logs']['userLOG'] if USR != "root" else root_log_file
    log_file = home_dir / ".local" / "state" / "recentchanges" / "logs" / log_file

    return ConfigData(home_dir, xdg_runtime, toml_file, json_file, log_file, uid, gid, config, EXCLDIRS, nogo, filterout_list, driveTYPE, ll_level)


def return_info(file_path, st, symlink, link_target, logger):
    fmt = "%Y-%m-%d %H:%M:%S"
    target = sym = hardlink = None

    if symlink:
        sym = "y"
        target = link_target

    mode = oct(stat.S_IMODE(st.st_mode))[2:]  # '644' # stat.filemode(st.st_mode)  '-rw-r--r--'
    inode = st.st_ino

    # if stat.S_ISREG(st.st_mode):
    hardlink = st.st_nlink
    try:
        owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        emit_log("DEBUG", f"set_stat failed to convert uid to user name for file: {file_path}", logger)
        owner = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        emit_log("DEBUG", f"set_stat failed to convert gid to group name for file: {file_path}", logger)
        group = str(st.st_gid)

    m_epoch = st.st_mtime
    m_epoch_ns = st.st_mtime_ns
    c_epoch = st.st_ctime
    a_epoch = st.st_atime
    m_dt = epoch_to_date(m_epoch)
    m_time = m_dt.strftime(fmt)
    c_time = epoch_to_str(c_epoch)
    a_time = epoch_to_str(a_epoch)
    size = st.st_size
    return sym, target, mode, inode, hardlink, owner, group, m_dt, m_epoch_ns, m_time, c_time, a_time, size
