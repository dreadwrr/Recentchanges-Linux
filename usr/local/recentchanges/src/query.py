#!/usr/bin/env python3
import os
import sqlite3
import sys
import tempfile
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from .gpgcrypto import decr
from .gpgcrypto import gpg_can_decrypt
from .gpgkeymanagement import delete_gpg_keys
from .gpgkeymanagement import reset_gpg_keys
from .pyfunctions import is_integer
from .rntchangesfunctions import name_of
# from .rntchangesfunctions import cprint
# 02/04/2026


# see pyfunctions.py cache clear patterns for db


def blank_count(curs):
    curs.execute('''
        SELECT COUNT(*)
        FROM logs
        WHERE (timestamp IS NULL OR timestamp = '')
        AND (filename IS NULL OR filename = '')
        AND (inode IS NULL OR inode = '')
        AND (accesstime IS NULL OR accesstime = '')
        AND (checksum IS NULL OR checksum = '')
        AND (filesize IS NULL OR filesize = '')
    ''')
    count = curs.fetchone()
    return count[0]


def dexec(cur, actname, limit):
    query = '''
    SELECT *
    FROM stats
    WHERE action = ?
    ORDER BY timestamp DESC
    LIMIT ?
    '''
    cur.execute(query, (actname, limit))
    return cur.fetchall()


def averagetm(conn, cur):
    cur.execute('''
    SELECT timestamp
    FROM logs
    ORDER BY timestamp ASC
    ''')
    timestamps = cur.fetchall()
    total_minutes = 0
    valid_timestamps = 0
    for timestamp in timestamps:
        if timestamp and timestamp[0]:
            current_time = datetime.strptime(timestamp[0], "%Y-%m-%d %H:%M:%S")
            total_minutes += current_time.hour * 60 + current_time.minute
            valid_timestamps += 1
    if valid_timestamps > 0:
        avg_minutes = total_minutes / valid_timestamps
        avg_hours = int(avg_minutes // 60)
        avg_minutes = int(avg_minutes % 60)
        avg_time = f"{avg_hours:02d}:{avg_minutes:02d}"
        return avg_time
    return "N/A"


def main(app_install, home_dir, user, email, reset=None, database=None, log_fn=print):

    pst_data = home_dir / ".local" / "share" / "recentchanges"
    flth = pst_data / "flth.csv"
    dbtarget = pst_data / "recent.gpg"
    CACHE_F = pst_data / "ctimecache.gpg"
    CACHE_S = pst_data / "systimeche.gpg"

    output = name_of(dbtarget, '.db')

    flth = str(flth)
    dbtarget = str(dbtarget)

    agnostic_check = False
    no_key = False
    result = False

    if reset:

        return delete_gpg_keys(user, email, dbtarget, CACHE_F, CACHE_S)

    try:

        with tempfile.TemporaryDirectory(dir='/tmp') as tempdir:

            if database:
                dbopt = database
                result = True

            else:

                #  the search runs as root check that there are no problems there
                if not gpg_can_decrypt(user, dbtarget):
                    agnostic_check = True

                dbopt = os.path.join(tempdir, output)

                result = decr(dbtarget, dbopt, user)

                # can easily break if trying to automate fixing keys. let the user do it if wanted.

            if result:

                # User has key root doesnt. give instructions to fix it or just delete the pair to reset
                if agnostic_check:
                    reset_gpg_keys(user, email, dbtarget, CACHE_F, CACHE_S, agnostic_check, no_key=no_key)

                if os.path.isfile(dbopt):
                    with sqlite3.connect(dbopt) as conn:
                        cur = conn.cursor()
                        # optionally run database commands
                        # cur.execute("DELETE FROM logs WHERE filename = ?", ('/home/guest/Downloads/Untitled' ,))
                        # conn.commit()
                        atime = averagetm(conn, cur)
                        ctext = "\033[36mSearch breakdown \033[0m"
                        log_fn(ctext)
                        cur.execute("""
                            SELECT
                            datetime(AVG(strftime('%s', accesstime)), 'unixepoch') AS average_accesstime
                            FROM logs
                            WHERE accesstime IS NOT NULL;
                        """)
                        result = cur.fetchone()
                        average_accesstime = result[0] if result and result[0] is not None else None
                        if average_accesstime:
                            log_fn(f'Average access time: {average_accesstime}')
                        log_fn(f'Avg hour of activity: {atime}')
                        cnt = blank_count(cur)
                        cur.execute('''
                        SELECT filesize
                        FROM logs
                        ''')
                        filesizes = cur.fetchall()
                        total_filesize = 0
                        valid_entries = 0
                        for filesize in filesizes:
                            if is_integer(filesize):
                                total_filesize += int(filesize[0])
                                valid_entries += 1
                        if valid_entries > 0:
                            avg_filesize = total_filesize / valid_entries
                            avg_filesize_kb = int(avg_filesize / 1024)
                            log_fn(f'Average filesize: {avg_filesize_kb} KB')
                            log_fn("")
                        log_fn(f'Searches {cnt}')  # count
                        log_fn("")
                        cur.execute('''
                        SELECT filename
                        FROM logs
                        WHERE TRIM(filename) != ''
                        ''')  # Ext
                        filenames = cur.fetchall()
                        extensions = []
                        for entry in filenames:
                            filepath = Path(entry[0])
                            filename = filepath.name
                            if filename.startswith('.') or '.' not in filename:
                                ext = '[no extension]'
                            else:
                                ext = '.' + '.'.join(filename.split('.')[1:])
                            extensions.append(ext)
                        if extensions:
                            counter = Counter(extensions)
                            top_3 = counter.most_common(3)
                            ctext = "\033[36mTop extension\033[0m"
                            log_fn(ctext)
                            for ext, count in top_3:
                                log_fn(f"{ext}")
                        log_fn("")
                        directories = [os.path.dirname(filename[0]) for filename in filenames]  # top directories
                        directory_counts = Counter(directories)
                        top_3_directories = directory_counts.most_common(3)
                        ctext = "\033[36mTop 3 directories\033[0m"
                        log_fn(ctext)
                        for directory, count in top_3_directories:
                            log_fn(f'{count}: {directory}')
                        log_fn("")
                        cur.execute("SELECT filename FROM logs WHERE TRIM(filename) != ''")  # common file 5
                        filenames = [row[0] for row in cur.fetchall()]  # end='' prevents extra newlines
                        filename_counts = Counter(filenames)
                        top_5_filenames = filename_counts.most_common(5)
                        ctext = "\033[36mTop 5 created\033[0m"
                        log_fn(ctext)
                        for file, count in top_5_filenames:
                            log_fn(f'{count} {file}')
                        top_5_modified = dexec(cur, 'Modified', 5)
                        filenames = [row[3] for row in top_5_modified]
                        filename_counts = Counter(filenames)
                        top_5_filenames = filename_counts.most_common(5)
                        ctext = "\033[36mTop 5 modified\033[0m"
                        log_fn(ctext)
                        for filename, count in top_5_filenames:
                            filename = filename.strip()
                            log_fn(f'{count} {filename}')
                        top_7_deleted = dexec(cur, 'Deleted', 7)
                        filenames = [row[3] for row in top_7_deleted]
                        filename_counts = Counter(filenames)
                        top_7_filenames = filename_counts.most_common(7)
                        ctext = "\033[36mTop 7 deleted\033[0m"
                        log_fn(ctext)
                        for filename, count in top_7_filenames:
                            filename = filename.strip()
                            log_fn(f'{count} {filename}')
                        top_7_writen = dexec(cur, 'Overwrite', 7)
                        filenames = [row[3] for row in top_7_writen]
                        filename_counts = Counter(filenames)
                        top_7_filenames = filename_counts.most_common(7)
                        ctext = "\033[36mTop 7 overwritten\033[0m"
                        log_fn(ctext)
                        for filename, count in top_7_filenames:
                            filename = filename.strip()
                            log_fn(f'{count} {filename}')
                        top_5_nsf = dexec(cur, 'Nosuchfile', 5)
                        filenames = [row[3] for row in top_5_nsf]
                        filename_counts = Counter(filenames)
                        if filename_counts:
                            top_5_filenames = filename_counts.most_common(5)
                            ctext = "\033[36mNot actually a file\033[0m"
                            log_fn(ctext)
                            for filename, count in top_5_filenames:
                                log_fn(f'{count} {filename}')
                        log_fn("")
                        ctext = "\033[1;32mFilter hit\033[0m"
                        log_fn(ctext)
                        if os.path.isfile(flth):
                            with open(flth, 'r') as file:
                                for line in file:
                                    if database:
                                        log_fn(line)
                                    else:
                                        print(line, end='')
                        return 0
                else:
                    # no recent.db file permission error abort so sql doesnt make an empty database
                    log_fn(f"Unable to locate database: {dbopt}")

            # User has no key
            elif not database and result is None:
                no_key = True

                if user != 'root' and not agnostic_check:

                    # Root has key user doesnt. try to resolve key problem
                    reset_gpg_keys(user, email, dbtarget, CACHE_F, CACHE_S, agnostic_check, no_key=no_key)

                else:
                    ctime_path = CACHE_F.name
                    log_fn(f"No key for {dbtarget} or {ctime_path}. if unable to fix delete to reset")

            else:

                if os.path.isfile(dbtarget):
                    log_fn(f'Find out why not decrypting. If unable to fix call: recentchanges reset  . unable to decrypt file: {dbtarget}')

                # else if no recent.gpg there was an exception
                return 1

    except Exception as e:
        log_fn(f"Exception while running query {type(e).__name__}: {e}  \n {traceback.format_exc()}")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: query.py <app_install> <home_dir> <user> <email>")
        sys.exit(0)

    app_install, home_dir, user, email = sys.argv[1:5]

    reset = sys.argv[5] if len(sys.argv) > 5 else None
    database = sys.argv[6] if len(sys.argv) > 6 else None

    sys.exit(main(app_install, home_dir, user, email, reset=reset, database=database))
