import csv
import fnmatch
import re
from datetime import datetime
from .configfunctions import not_absolute


# terminal and hardlink suppression
suppress_terminal = [
    r'mozilla',
    r'\.mozilla',
    r'chromium-ungoogled',
    r'/home/{{user}}/\.config/recentchanges/config\.bak'
    # r'google-chrome',
]


# patterns to delete from db.
cache_clear = [
    "%caches%",
    "%cache2%",
    "%Cache2%",
    "%.cache%",
    "%share/Trash%",
    "%home/{{user}}/.local/state/wireplumber%",
    "%root/.local/state/wireplumber%",
    "%usr/share/mime/application%",
    "%usr/share/mime/text%",
    "%usr/share/mime/image%",
    "%release/cache%",
]


# filter hits to reset on db cache clear. copy literal items from /usr/local/recentchanges/filter.py to reset to 0
flth_literal_patterns = [
    r'\.cache',
    r'/home/{{user}}/\.config',
    r'/home/{{user}}/\.Xauthority',
    r'/root/\.Xauthority',
    r'/home/{{user}}/\.local/state/wireplumber',
    r'/root/\.local/state/wireplumber'
]


def suppress_list(escaped_user):
    suppress_list = [p.replace("{{user}}", escaped_user) for p in suppress_terminal]
    compiled = [re.compile(p) for p in suppress_list]
    return compiled


def get_delete_patterns(usr):
    patterns = [p.replace("{{user}}", usr) for p in cache_clear]
    return patterns


def reset_csvliteral(csv_file):

    patterns_to_reset = flth_literal_patterns
    try:
        with open(csv_file, newline='') as f:
            reader = csv.reader(f)
            rows = list(reader)
        for row in rows[1:]:
            if row[0] in patterns_to_reset:
                row[1] = '0'
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    except (FileNotFoundError, PermissionError):
        print(f"nfs permission error on {csv_file} reset_csvliteral.")
        pass


def user_path(settingName, theusr):

    if isinstance(settingName, list):
        processed = []
        if theusr == "root":
            for p in settingName:
                out = p
                if "{{user}}" in p and not p.startswith("{{user}}"):
                    _, end = p.split("{{user}}", 1)
                    out = "/{{user}}"
                    if not_absolute(p, quiet=True):
                        out = "{{user}}"
                    out = out + end
                processed.append(out)
        else:
            processed = settingName
        return [s.replace("{{user}}", theusr) for s in processed]
    elif isinstance(settingName, str):
        if theusr == "root":
            if "{{user}}" in settingName and not settingName.startswith("{{user}}"):
                _, end = settingName.split("{{user}}", 1)
                out = "/root"
                if not_absolute(settingName, quiet=True):
                    out = "root"
                return out + end
        return settingName.replace("{{user}}", theusr)
    else:
        raise ValueError(f"Invalid type for settingName: {type(settingName).__name__}, expected str or list")


# Convert SQL-like % wildcard to fnmatch *
def matches_any_pattern(s, patterns):

    for pat in patterns:
        pat = pat.replace('%', '*')
        if fnmatch.fnmatch(s, pat):
            return True
    return False


class cprint:
    CYAN = "\033[36m"
    RED = "\033[31m"
    GREEN = "\033[1;32m"
    BLUE = "\033[34m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    WHITE = "\033[37m"
    RESET = "\033[0m"

    @staticmethod
    def colorize(color, msg, fp=None):
        """Return ANSI string; print to stdout if fp is None."""
        text = f"{color}{msg}{cprint.RESET}"
        if fp is None:
            print(text)  # default: print to console
        else:
            return text  # just return string, don’t print

    @staticmethod
    def cyan(msg, fp=None): return cprint.colorize(cprint.CYAN, msg, fp)
    @staticmethod
    def red(msg, fp=None): return cprint.colorize(cprint.RED, msg, fp)
    @staticmethod
    def green(msg, fp=None): return cprint.colorize(cprint.GREEN, msg, fp)
    @staticmethod
    def blue(msg, fp=None): return cprint.colorize(cprint.BLUE, msg, fp)
    @staticmethod
    def yellow(msg, fp=None): return cprint.colorize(cprint.YELLOW, msg, fp)
    @staticmethod
    def magenta(msg, fp=None): return cprint.colorize(cprint.MAGENTA, msg, fp)
    @staticmethod
    def white(msg, fp=None): return cprint.colorize(cprint.WHITE, msg, fp)
    @staticmethod
    def reset(msg, fp=None): return cprint.colorize(cprint.RESET, msg, fp)

    @staticmethod
    def plain(msg, fp=None):
        if fp is None:
            print(msg)  # default: print to console
        else:
            return msg  # just return string without printing


def epoch_to_str(epoch, fmt="%Y-%m-%d %H:%M:%S"):
    try:
        dt = datetime.fromtimestamp(float(epoch))
        return dt.strftime(fmt)
    except (TypeError, ValueError):
        return None


def epoch_to_date(epoch):
    try:
        return datetime.fromtimestamp(float(epoch))
    except (TypeError, ValueError):
        return None


# obj from obj or str
def parse_datetime(value, fmt="%Y-%m-%d %H:%M:%S"):
    if isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value).strip(), fmt)
        # return dt.strftime(fmt)
    except (ValueError, TypeError, AttributeError):
        return None


# encoding
def ap_decode(s):
    s = s.replace('\\ap0A', '\n')
    s = s.replace('\\ap09', '\t')
    s = s.replace('\\ap22', '"')
    # s = s.replace('\\ap24', '$')
    s = s.replace('\\ap20', ' ')
    s = s.replace('\\ap5c', '\\')
    return s


def escf_py(filename):
    filename = filename.replace('\\', '\\ap5c')
    filename = filename.replace('\n', '\\\\n')
    # filename = filename.replace('"', '\\"')
    # filename = filename.replace('\t', '\\t')
    # filename = filename.replace('$', '\\$')
    return filename


def unescf_py(s):
    s = s.replace('\\\\n', '\n')
    # s = s.replace('\\"', '"')
    # s = s.replace('\\t', '\t')
    # s = s.replace('\\$', '$')
    s = s.replace('\\ap5c', '\\')
    return s
# end encoding


def is_integer(value):
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def is_valid_datetime(value, fmt):
    try:
        datetime.strptime(str(value).strip(), fmt)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def date_from_stat(st, fmt):
    a_mod = st.st_mtime
    afrm_dt = datetime.fromtimestamp(a_mod)  # datetime.utcfromtimestamp(a_mod)
    afrm_str = afrm_dt.strftime(fmt)
    return afrm_dt, afrm_str


def new_meta(record, metadata):
    return (
        record[0] != metadata[0] or  # onr
        record[1] != metadata[1] or  # grp
        record[2] != metadata[2]  # perm
    )


def sys_record_flds(record, sys_records, prev_count):
    sys_records.append((
        record[0],  # timestamp
        record[1],  # filename
        record[2],  # changetime
        record[3],  # inode
        record[4],  # accesstime
        record[5],  # checksum
        record[6],  # filesize
        record[7],  # symlink
        record[8],  # owner
        record[9],  # group
        record[10],  # permissions
        record[11],  # casmod
        record[12],  # target
        record[13],  # lastmodified
        record[14],  # hardlinks
        prev_count + 1,  # count
        record[15]  # mtime_us
    ))
