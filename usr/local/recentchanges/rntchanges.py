#!/usr/bin/env python3
# v5.0                                                       02/22/2026
# This script is the entry point for recentchanges. The inv flag is passed in from from /usr/local/recentchanges/filteredsearch script from /usr/local/bin/rnt symlink
#
# There are 2 positional arguments. a third is the inv flag and is filtered out before executing script.
# the filtered arg just changes a regular search to the inverse for recentchanges search, recentchanges search n, recentchanges search myfile
#
# for recentchanges the arguments shift. as its `recentchanges` or `recentchanges n` and the filter arg doesnt apply. There is a SRC tag which will make a .xzm
# from a root directory with the most recent files.
# recentchanges takes 1 argument the time n or no arguments for 5 minutes.
#
# recentchanges search - output to Downloads unfiltered system files and tmp files. Also search for newer than file filtered. if called from rnt symlink its filtered system files
# and unfiltered newer than.
# `query` - show stats from the database from past searches
#
# recentchanges - output to /tmp unfiltered system files. No tmp files.


# argone - the search time for `recentchanges` or the keyword search for `recentchanges search` or keyword query to get stats from database
# argtwo - search time for `recentchanges search`
# argf - inv flag from rnt symlink
import sys
from src.configfunctions import find_install
from src.configfunctions import get_config
from src.configfunctions import get_user
from src.configfunctions import load_toml
from src.query import main as query_main
from src.recentchangessearch import main as recentchanges_main


# Handle inv flag
def filter_invflag(argv, pad_length=5):

    arge = ["" if item == "inv" else item for item in argv]
    argf = "filtered" if "inv" in argv else ""

    if len(arge) < pad_length:
        arge.extend([""] * (pad_length - len(arge)))
    return arge, argf


def main(argv):

    # original_user = os.environ.get('SUDO_USER')

    inv_flag = "inv" in argv
    max_len = 7 if inv_flag else 6
    arglen = len(argv)
    if arglen > max_len:
        if inv_flag:
            print("Incorrect usage. max from rnt 7. provided: ", len(argv) - 1)
        else:
            print("Incorrect usage. max args 6. provided: ", len(argv) - 1)
        print("Required <username> <PWD> <whoami>")
        print("please call from /usr/local/bin/recentchanges")
        return 1
    elif arglen < 3:
        print("Incorrect usage. <username> <PWD> please call from recentchanges")
        return 1

    USR = argv[1]
    user_name = get_user()
    appdata_local = find_install()

    toml_file, json_file, home_dir, xdg_config, xdg_runtime, USR, uid, gid = get_config(appdata_local, USR)
    config = load_toml(toml_file)
    if not config:
        return 1
    email = config['backend']['email']

    PWD = argv[2]
    args = argv[3:]

    arge, argf = filter_invflag(args)  # filter out the invflag set argf to `filtered`. passed from filteredsearch

    argone = arge[0] or "noarguser"
    THETIME = arge[1] or "noarguser"

    if argone == "query":

        return query_main(appdata_local, home_dir, USR, email)

    elif argone == "reset":

        return query_main(appdata_local, home_dir, USR, email, reset="resetgpg")

    if user_name == 'root':

        if argone == "search":  # recentchanges search
            return recentchanges_main(argone, THETIME, USR, PWD, argf, "")

        else:  # recentchanges
            argf = "bnk"

            SRCDIR = "SRC" if "SRC" in arge[:2] else "noarguser"

            THETIME = arge[0] or "noarguser"  # Shift for this script
            if THETIME == "SRC":
                THETIME = arge[1] or "noarguser"

            if THETIME == "search":
                print("Exiting not a search.")
                return 1

            # Final normalization
            if THETIME == "SRC":
                THETIME = "noarguser"

            return recentchanges_main(THETIME, SRCDIR, USR, PWD, argf, "rnt")
    else:
        print("Please call as root from recentchanges")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
