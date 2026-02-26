import getpass
from .rntchangesfunctions import removefile
import glob
import logging
import os
import subprocess
import sys
import tempfile
import traceback
from typing import Any
from .configfunctions import get_user
from .rntchangesfunctions import name_of


def iskey(email):
    try:
        result = subprocess.run(
            ["gpg", "--list-secret-keys"],
            capture_output=True,
            text=True,
            check=True
        )
        return (email in result.stdout), result.stdout
    except subprocess.CalledProcessError as e:
        err = f"Error running gpg: {e}, type: {type(e).__name__} \n {e.stderr}"
        return None, err


# setup keypair called by set_recent_helper script
def import_key(argv):
    if len(argv) < 2:
        print("import_key <keyfile> <email>")
        return 1
    keyfile = argv[0]
    email = argv[1]
    if not os.path.isfile(keyfile):
        print("import_key Missing keyfile: ", keyfile)
        return 1

    passphrase = None
    if "--passphrase-fd" in argv:
        idx = argv.index("--passphrase-fd")
        fd = int(argv[idx + 1])
        print("reading from file descriptor: ", fd)
        passphrase = sys.stdin.read().strip()

    if not passphrase:
        print("import_key No passphrase")
        return 1

    try:
        r, w = os.pipe()
        os.write(w, passphrase.encode())
        os.close(w)

        subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--pinentry-mode", "loopback",
                "--passphrase-fd", "3",
                "--import",
                str(keyfile),
            ],
            pass_fds=(r,),
            stdin=subprocess.DEVNULL,
            check=True
        )  # works not as secure as passing passphrase in commandline. conversly putting the passphrase to a file although safer is not ideal
        # with open(ftarget, "rb") as keyfile:
        # subprocess.run(
        #     [
        #         "gpg",
        #         "--batch",
        #         "--yes",
        #         "--pinentry-mode", "loopback",
        #         "--passphrase", passphrase,
        #         "--import",
        #     ],
        #     stdin=keyfile,
        #     check=True
        # )
        input_data = "trust\n5\ny\nquit\n"

        result = subprocess.run(["sudo", "gpg", "--command-fd", "0", "--edit-key", email], input=input_data, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print("failed to import", keyfile, " GPG failed:", result.stderr)
        return 0

    except subprocess.CalledProcessError as e:
        print(f"import_key failed to import from keyfile {keyfile} return_code: {e.returncode} err: {e}")
        combined = "\n".join(filter(None, [
            e.stdout.decode(errors="replace") if e.stdout else "",
            e.stderr.decode(errors="replace") if e.stderr else "",
        ]))
        if combined:
            print("[GPG OUTPUT]\n" + combined)
        return 1
    finally:
        try:
            os.close(r)
        except Exception:
            pass


# same as bash rntchangesfunctions. setup keypair for user and root
def genkey(appdata_local, USR, email, name, TEMPD, is_polkit, passphrase=None):

    if not passphrase:
        passphrase = getpass.getpass("Enter passphrase for new GPG key: ")
    p = passphrase
    if not p:
        return False

    params = f"""%echo Generating a GPG key
Key-Type: RSA
Key-Length: 4096
Subkey-Type: RSA
Subkey-Length: 4096
Name-Real: {name}
Name-Email: {email}
Expire-Date: 0
Passphrase: {p}
%commit
%echo done
"""
    with tempfile.TemporaryDirectory(dir=TEMPD) as kp:

        ftarget = os.path.join(kp, 'keyparams.conf')

        try:

            with open(ftarget, "w", encoding="utf-8") as f:
                f.write(params)
            os.chmod(ftarget, 0o600)

            cmd = [
                "gpg",
                "--batch",
                "--pinentry-mode", "loopback",
                "--passphrase", p,
                "--generate-key"
            ]

            # Open the params file and pass it as stdin
            with open(ftarget, "rb") as param_file:
                subprocess.run(cmd, check=True, stdin=param_file)

        except subprocess.CalledProcessError as e:
            print(f"Failed to generate GPG key: {e}")
            if e.stderr:
                print(e.stderr.decode(errors="replace"))
            return False
        except Exception as e:
            print(f'Unable to make GPG key: {type(e).__name__} {e} {traceback.format_exc()}')
            return False
        finally:
            removefile(ftarget)
        if USR != 'root':
            keyfile = os.path.join(kp, "key.asc")
            try:
                try:

                    with open(keyfile, "wb") as f:
                        subprocess.run(
                            [
                                "gpg",
                                "--batch",
                                "--yes",
                                "--pinentry-mode", "loopback",
                                "--passphrase-fd", "0",
                                "--export-secret-keys",
                                "--armor",
                                email
                            ],
                            input=p.encode(),
                            stdout=f,
                            check=True
                        )

                    script_path = appdata_local / "main"
                    script_dir = os.path.dirname(script_path)

                    cmd = "pkexec" if is_polkit else "sudo"
                    result = subprocess.run(
                        [
                            cmd,
                            str(script_path),
                            "import",
                            str(keyfile),
                            str(email),
                            "--passphrase-fd", "0"
                        ],
                        input=p.encode(),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=script_dir,
                    )
                    stdout = result.stdout.decode(errors="replace")
                    stderr = result.stderr.decode(errors="replace")
                    if result.returncode != 0:
                        stdout = "STDOUT:\n" + stdout  # print any debug
                        stderr = "STDERR:\n" + stderr  # gpg prints to stderr
                    print(stdout)
                    print(stderr)

                except subprocess.CalledProcessError as e:
                    print(f"genkey failed to export keyfile: {keyfile} err: {e}")
                    combined = "\n".join(filter(None, [
                        e.stdout.decode(errors="replace") if e.stdout else "",
                        e.stderr.decode(errors="replace") if e.stderr else "",
                    ]))
                    if combined:
                        print("[OUTPUT]\n" + combined)
            except Exception as e:
                msg = f"failed to import keyfile {keyfile} error: {e}, {type(e).__name__}"
                print(msg)
                logging.error(msg, exc_info=True)
            removefile(keyfile)
        print(f"GPG key generated for {email}.")
        return True


# required for batch deleting keys
def get_key_fingerprint(email, no_key=False):
    cmd = ["gpg", "--list-keys", "--with-colons", email]
    if no_key:
        cmd = ["sudo"] + cmd
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    for line in result.stdout.split('\n'):
        if line.startswith('fpr:'):
            return line.split(':')[9]
    return None


def delete_gpg_keys(usr, email, dbtarget, CACHE_F, CACHE_S):

    def instruct_out():
        print("To import the key for one to the other to attempt to repair it, try the following. If it doesn't work delete the key pair and start over.")
        print("\nAs user or root:")
        print(f"gpg --batch --yes --pinentry-mode loopback --export-secret-keys --armor {email} > key.asc")
        print("user or root")
        print("gpg --batch --yes --pinentry-mode loopback --import key.asc")
        print("rm key.asc")
        print(f"gpg --edit-key {email}")
        print("trust")
        print("5")
        print("y")
        print("quit")

    def exec_delete_keys(usr, current_usr, email, fingerprint):
        silent: dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

        if usr == 'root':
            subprocess.run(["gpg", "--batch", "--yes", "--delete-secret-keys", fingerprint], **silent)
            subprocess.run(["gpg", "--batch", "--yes", "--delete-keys", fingerprint], **silent)
        else:
            subprocess.run(["gpg", "--batch", "--yes", "--delete-secret-keys", fingerprint], **silent)
            subprocess.run(["gpg", "--batch", "--yes", "--delete-keys", fingerprint], **silent)
            if current_usr == 'root':
                subprocess.run(["sudo", "-u", usr, "gpg", "--batch", "--yes", "--delete-secret-keys", fingerprint], **silent)
                subprocess.run(["sudo", "-u", usr, "gpg", "--batch", "--yes", "--delete-keys", fingerprint], **silent)
            else:
                subprocess.run(["sudo", "gpg", "--batch", "--yes", "--delete-secret-keys", fingerprint], **silent)
                subprocess.run(["sudo", "gpg", "--batch", "--yes", "--delete-keys", fingerprint], **silent)
        print("Keys cleared for", email, " fingerprint: ", fingerprint)

    while True:

        uinp = input(f"Warning recent.gpg will be cleared. Reset\\delete gpg keys for {email} (Y/N): ").strip().lower()
        if uinp == 'y':
            confirm = input("Are you sure? (Y/N): ").strip().lower()
            if confirm == 'y':

                result = False

                current_usr = get_user()

                # look in root for key
                fingerprint = get_key_fingerprint(email, no_key=True)
                if fingerprint:
                    result = True
                    # delete for user and root
                    exec_delete_keys(usr, current_usr, email, fingerprint)

                # look for key in user
                fingerprint = get_key_fingerprint(email, no_key=False)
                if fingerprint:
                    result = True
                    exec_delete_keys(usr, current_usr, email, fingerprint)

                systimeche = name_of(CACHE_S)
                file_path = os.path.dirname(CACHE_S)
                pattern = os.path.join(file_path, f"{systimeche}*")
                # delete ctimecache & db .gpg
                for r in (CACHE_F, dbtarget):
                    removefile(r)
                # delete profile .gpgs
                for filepath in glob.glob(pattern):
                    removefile(filepath)
                if result:
                    # print(f"\nDelete {dbtarget} if it exists as it uses the old key pair.")
                    return 1
                else:
                    print(f"No key found for {email}")
                    return 2

            else:
                instruct_out()
                return 0

        elif uinp == 'n':
            instruct_out()
            return 0
        else:
            print("Invalid input, please enter 'Y' or 'N'.")


def reset_gpg_keys(usr, email, dbtarget, CACHE_F, CACHE_S, agnostic_check, no_key=False):
    if agnostic_check is False and no_key is True:
        print("only root has key\n")
    elif agnostic_check is True and no_key is False:
        print("only user has key. Select n and manually import the key for root to fix it. or delete the key pair to reset state.\n")
    print("A problem was detected with key pair. ")
    return delete_gpg_keys(usr, email, dbtarget, CACHE_F, CACHE_S)
