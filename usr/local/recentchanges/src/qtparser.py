
#!/usr/bin/env python3
# flake8: noqa: E402
import sys
from src.dirwalker import main_entry as dirwalker_main
from src.findfile import main_entry as findfile_main
from src.gpgkeymanagement import import_key
from src.recentchangessearch import main as recentchanges_main
from src.recentchangessearchparser import build_subparser
from src.rntchanges import main as rntchanges_main
from src.qtfunctions import load_konsole
from src.qtfunctions import load_file_manager
from src.qtfunctions import kill_process
# 03/14/2026


def dispatch_internal(argv):
    arglen = len(argv)
    if arglen >= 3:
        script = argv[1].lower()
        args = argv[2:]
        cmd = args[0]   
        if arglen > 5:

            DISPATCH_MAP = {
                "dirwalker.py": {
                    "hardlink": 9,
                    "scan": 8,
                    "build": 7,
                    "downloads": 12,
                },
                "recentchangessearch.py": recentchanges_main,
                "findfile.py": findfile_main,
                "import": import_key
            }

            entry = DISPATCH_MAP.get(script)

            # uid_str = os.environ.get("PKEXEC_UID")
            # if uid_str:
            # usr_name = pwd.getpwuid(os.geteuid()).pw_name

            # set process group for SIGINT SIGTERM
            # os.setsid()
            # p_id = os.getpgid(0)  # print("pid",  p_id)

            if isinstance(entry, dict):
                if cmd not in entry:
                    print(
                        f"Invalid parameter for dirwalker; expected one of: "
                        f"{'/'.join(entry.keys())}, got {cmd}"
                    )
                    sys.exit(1)
                min_args = entry[cmd]
                if len(args) < min_args:
                    print(f"Not enough args for '{cmd}', expected {min_args}, got {len(args)}")
                    sys.exit(1)

                sys.exit(dirwalker_main(args))

            elif entry:

                if script == "recentchangessearch.py":
                    recent_args = build_subparser(script)
                    sys.exit(entry(*recent_args))
                elif script == "findfile.py":
                    sys.exit(entry(args))
                elif script == "import":
                    return entry(args)

        elif script == "run":
            if cmd == "filemanager":
                sys.exit(load_file_manager(*args[1:]))  # lclhome, popPATH=
            if cmd == "terminal":
                sys.exit(load_konsole(*args[1:]))  # lclhome, popPATH=
            if cmd == "kill":
                sys.exit(kill_process(*args[1:]))
    sys.exit(rntchanges_main(argv))
