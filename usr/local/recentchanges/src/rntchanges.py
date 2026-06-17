#!/usr/bin/env python3
# v5.0                                                       06/15/2026
# This script is the entry point for recentchanges. The inv flag is passed in from from /usr/local/recentchanges/filteredsearch script from /usr/local/bin/rnt symlink
#
# There are 2 positional arguments. a third is the inv flag
# the filtered arg just changes a regular search to the inverse for recentchanges search, recentchanges search n, recentchanges search myfile
#
# for recentchanges the arguments shift. as its recentchanges or recentchanges n. There is a SRC tag which will make a .xzm
# from a root directory with the most recent files.
#
# the main purpose is to output unfiltered system files and tmp files. 
#
# recentchanges - output to /tmp
# can take 1 argument the time n or no arguments for 5 minutes. 
# as well as the SRC tag recentchanges SRC 60, recentchanges 60 SRC or recentchanges SRC
#
# recentchanges search - output to Downloads 
# can take 1 argument the time n or no arguments for 5 minutes. 
# as well as newer than file with recentchanges search myfile or recentchanges search /home/guest/myfile. it is filtered rather than unfiltered and if called from rnt symlink its unfiltered
# .
# recentchanges query - show stats from the database from past searches
#
# recentchanges reset - delete gpg key and gpg files and prompt to reset config files
#
# argone - the search time for `recentchanges` or the keyword search for `recentchanges search` or keyword query to get stats from database
# argtwo - search time for `recentchanges search`
# argf - inv flag from rnt symlink
# flake8: noqa: E402
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.query import main as query_main
from src.recentchangessearch import main as recentchanges_main


def main(argv):
    max_len = 6
    arglen = len(argv)
    if arglen > max_len:
        print("Incorrect usage. max args 6. provided: ", arglen)
        print("Required <username> <PWD>")
        print("please call from /usr/local/bin/recentchanges")
        return 1
    elif arglen < 3:
        print("Incorrect usage. <username> <PWD> please call from /usr/local/bin/recentchanges")
        return 1

    usr = argv[1]
    pwd = argv[2]

    argone = argv[3] if len(sys.argv) > 3 and argv[3] else "noarguser"
    argtwo = argv[4] if len(sys.argv) > 4 and argv[4] else "noarguser"

    srcDIR = ""
    method = ""
    argf = ""

    if argone == "inv":
        argf="filtered"
        argone="noarguser"
    elif argtwo == "inv":
        argf="filtered"
        argtwo="noarguser"
    elif "inv" in argv:
        argf = "filtered"

    if argone == "query" or argone == "reset":
        reset = argone == "reset"
        return query_main(user=usr, reset=reset)

    elif argone == "search":  # recentchanges search
        thetime = argtwo
        return recentchanges_main(argone, thetime, usr, pwd, argf, method)

    else:  # recentchanges

        thetime = argone  # shift for recentchanges
        method = "rnt"

        if thetime == "SRC":
            thetime = argtwo if argtwo != "SRC" else "noarguser"

        if argtwo == "search":
            print("Exiting not a search.")
            return 1

        srcDIR = "SRC" if "SRC" in sys.argv else "noarguser"

        return recentchanges_main(thetime, srcDIR, usr, pwd, argf, method)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
