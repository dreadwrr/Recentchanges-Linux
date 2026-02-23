from pathlib import Path
from .dirwalkerfunctions import check_precedence
from .dirwalkerfunctions import check_specified_paths
# profile template created from xzm layouts. implemented for Qt python


class XzmProfile:

    # hash all in
    PATH = [
        "home",
        "root",
        "etc"
    ]

    # "home/user/lib",
    LIBRARY = [
        "lib",
        "lib64",
        "usr/lib",
        "usr/lib64",
        "var/lib"
    ]

    BINARY = [
        "bin",
        "usr/bin",
        "usr/sbin",
        "etc",
        "sbin",
        "opt/porteus-scripts"
    ]

    def __init__(self, basedir="/", suppress=False):

        ch = "/mnt/live/memory/images"
        xzms = ['003', '002', '001']

        self.path_set = tuple()
        self.library_set = tuple()
        self.binary_set = tuple()
        self.path_exist = []
        self.lib_exist = []
        self.bin_exist = []

        self.layers = []
        for layer in xzms:
            p = f"{layer}-*"
            files = list(Path(ch).glob(p))
            self.layers.extend(files)

        self.path_tup, self.path_exist = check_specified_paths(basedir, self.PATH, "proteusPATHS", suppress)
        self.library_tup, self.lib_exist = check_specified_paths(basedir, self.LIBRARY, "LIBRARY paths", suppress)
        self.binary_tup, self.bin_exist = check_specified_paths(basedir, self.BINARY, "BINARY paths", suppress)
        check_precedence(self.library_tup, self.binary_tup, suppress)

    def create_xzm_baseline(self, suffix, json_file):
        """ build accurate list as some paths might not exist on the system """

        # template
        #     "binary bin etc sbin usr opt/porteus-scripts",
        #     "path etc home root",
        #     "library lib lib64 usr/lib usr/lib64 var/lib"

        extn, parts = [], []

        for item in self.path_exist:
            parts.append(item)
        path_str = ' '.join(parts)
        bin_str = ' '.join(self.bin_exist)
        lib_str = ' '.join(self.lib_exist)
        extn.append("binary " + bin_str)
        extn.append("path " + path_str)
        extn.append("library " + lib_str)
        return extn
