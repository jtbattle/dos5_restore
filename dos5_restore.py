# This script can list or extract the contents of a set of DOS 5.0 BACKUP files.
# I wrote it because while I can use DOSBOX to run RESTORE, it doesn't work if
# the backup spans more than one floppy disk image. This is because during the
# restore process a sequence of disk images must be mounted in turn, but DOSBOX
# requires running a pair of commands from the DOS command line:
#    mount -u a               -- unmount current virtual disk from a: drive
#    imgmount a "disk002.img" -- mount another virtual disk on a: drive
#
# This script doesn't operate on virtual floppy disk images, but instead on
# the extracted CONTROL.NNN and BACKUP.NNN files. In my case, I used a kryoflux
# card to capture the floppy disk images, then I used winimage to extract the
# backup files to a common directory.
#
# Word of warning: this script served my purposes, but has seen use for only
# a couple of backup disk sets. It is quite possible that other backup disks
# will expose bugs in this program. Also, I wasn't terribly consistent about
# handling unexpected/error cases. Sometimes you get an error message, and
# other times just an assert.
#
# The structure of the BACKUP control file was found here:
# http://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/dos/backup/brtecdoc.htm
# Note the offsets given in the file entry table has some errors.
#
# The attr byte is unknown, but looking at this wikipedia page:
# https://en.wikipedia.org/wiki/Design_of_the_FAT_file_system#Directory_entry
# is perhaps a good guess. Namely, these might apply:
#     0x01 - read only
#     0x02 - hidden
#     0x04 - system
#     0x20 - archive
# indeed, in the one backup I've inspected, files are either 0x00 or 0x20

# License
# -----------------------
# Copyright (c) 2020 Jim Battle
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Version history
# -----------------------
# version 1.0 -- 2020/11/27 -- first release

import sys
import re
import argparse
import glob
import os
import os.path
import time
import datetime
from pathlib import Path            # Python 3.5 or later
from dataclasses import dataclass   # Python 3.7 or later

# =============================================================================
# process control file header block
# =============================================================================
# Offset  Size       Contents
# ------  ---------  ----------------------------------------------------------
# 0x0000    1 byte   0x8B, length of the header record, including this byte
# 0x0001    8 bytes  The signature "BACKUP  "
# 0x0009    1 byte   Number of the backup disk (sequence), same as the extension
# 0x000A  128 bytes  Unknown, all zero bytes
# 0x008A    1 byte   0xFF, indicator if last disk in backup sequence

class ControlHeader:
    def __init__(self, blk):
        # explode fields
        blk_len = blk[0]
        assert len(blk) == blk_len
        assert blk_len == 0x8b
        blk_signature  = blk[0x01:0x09]
        blk_seq        = blk[0x09]
        blk_zeros      = blk[0x0a:0x8a]
        blk_sentinel   = blk[0x8a]

        # check for consistency
        assert blk_signature == b'BACKUP  '
        for byt in blk_zeros:
            assert byt == 0x00
        assert blk_sentinel in (0x00, 0xFF)

        # export fields
        self.seq   = blk_seq
        self.final = blk_sentinel == 0xFF   # last disk of backup set

# =============================================================================
# process directory entry
# =============================================================================
# Offset  Size       Contents
# ------  ---------  ----------------------------------------------------------
# 0x0000    1 byte   0x46, length of the entry record, including this byte
# 0x0001   63 bytes  Directory path name (zero padded ?), root is 0x00
# 0x0040    2 bytes  1 word, number entries in this directory
# 0x0042    4 bytes  1 long (?), 0xFFFFFFFF

class ControlDirectory:
    def __init__(self, blk):
        # explode fields
        blk_len = blk[0]
        assert len(blk) == blk_len
        assert blk_len == 0x46
        blk_path    = blk[0x01:0x40]
        blk_entries = blk[0x40:0x42]
        blk_unknown = blk[0x42:0x46]

        # check for consistency
        #                  hex       signed little-endian
        # control.001-003: FFFFFFFF       -1
        # control.004:     11050000     1297
        # control.005-006  15010000      277
        # control.007:     03020000      203
        # control.008:     FFFFFFFF       -1
        # control.009:     15010000      277
        # control.010-011: FFFFFFFF       -1
        # control.012:     CF020000      719
        # control.013:     FFFFFFFF       -1
        # I don't see a pattern or understand what it might mean.
        # woudl
        # assert blk_unknown == b'\xff\xff\xff\xff'

        # export fields
        self.path    = blk_path.decode('ascii').rstrip(' \x00')
        self.entries = int.from_bytes(blk_entries, byteorder='little')

# =============================================================================
# process file entry
# =============================================================================
# Offset  Size       Contents
# ------  ---------  ----------------------------------------------------------
# 0x0000    1 byte   0x22, length of the entry record, including this byte
# 0x0001   12 bytes  File name
# 0x000D    1 byte   Unknown, Flag for complete (03h) or split (02h) file
# 0x000E    4 bytes  1 long, original file size
# 0x0012    2 bytes  1 word, sequence/part of the backup file (1= first/complete, 2,3..=part of the file
# 0x0014    4 bytes  1 long, offset into BACKUP.??? File
# 0x0018    4 bytes  1 long, saved length in the BACKUP.??? File
# 0x001C    1 byte   File attributes
# 0x001D    1 byte   Unknown
# 0x001E    4 bytes  1 long,  file time/date stamp (DOS format, packed structure)

class ControlFile:
    def __init__(self, blk):
        # explode fields
        blk_len = blk[0]
        assert len(blk) == blk_len
        assert blk_len == 0x22
        blk_fname    = blk[0x01:0x0d]
        blk_complete = blk[0x0d]
        blk_osize    = blk[0x0e:0x12]
        blk_seq      = blk[0x12:0x14]
        blk_offset   = blk[0x14:0x18]
        blk_length   = blk[0x18:0x1C]
        blk_attr     = blk[0x1C]
        blk_unknown  = blk[0x1D]
        blk_date     = blk[0x1E:0x22]

        # check for consistency
        assert blk_complete in (0x02, 0x03)

        # export fields
        self.fname      = blk_fname.decode('ascii').rstrip('\x00')
        self.complete   = blk_complete == 0x03
        self.final_size = int.from_bytes(blk_osize,  byteorder='little')
        self.seq        = int.from_bytes(blk_seq,    byteorder='little')
        self.offset     = int.from_bytes(blk_offset, byteorder='little')
        self.length     = int.from_bytes(blk_length, byteorder='little')
        self.attr       = blk_attr
        self.date       = DOSdate(blk_date)

# =============================================================================
# utility routines
# =============================================================================

# https://en.wikipedia.org/wiki/Design_of_the_FAT_file_system#Directory_entry
#
# For the timestamp, the same wiki page shows a 16b encoding for time of day
#    bits  4:0  -- seconds/2, 0-29 (that is, it has a 2 second granularity)
#    bits 10:5  -- minutes, 0-59
#    bits 15:11 -- hours, 0-23
#
# For the day, the 16b encoding for day and year is
#    bits  4:0 -- day, 1-31
#    bits  8:5 -- month, 1-12
#    bits 15:9 -- year, 1980+n
#
# I'm not sure that BACKUP/RESTORE used this same encoding, but it
# produces timestamps that look plausible

# take a 4 byte encoding of date and time of day and munge into useful formats
# sorry, this is US-centric localization: 12hr am/pm, and month/day/year
class DOSdate:
    def __init__(self, blk):
        assert len(blk) == 4
        tod_16b = blk[0] + 256*blk[1]
        doy_16b = blk[2] + 256*blk[3]
        self.tod_seconds = (tod_16b >>  0) & 0x1F
        self.tod_minutes = (tod_16b >>  5) & 0x3F
        self.tod_hours   = (tod_16b >> 11) & 0x1F
        self.doy_day     = (doy_16b >>  0) & 0x1F
        self.doy_month   = (doy_16b >>  5) & 0x0F
        self.doy_year    = ((doy_16b >> 9) & 0x7F) + 1980

        am_pm = 'AM' if self.tod_hours < 12 else 'PM'
        tmp_hours = self.tod_hours if self.tod_hours <= 12 else (self.tod_hours - 12)
        self.as_str = "%02d/%02d/%4d %02d:%02d %s" % (
                        self.doy_month, self.doy_day, self.doy_year,
                        tmp_hours, self.tod_minutes, am_pm)

# returns true if the string in fname matches the specified glob pattern.
# the glob module works on actual files, but we want to work on a string,
# so the glob pattern is modified to a regexp and then re is used to match.
def globMatch(fname, pat):
    rePat = re.sub(r'\.', '\.', pat)     # literal '.'
    rePat = re.sub(r'\*', '.*', rePat)   # zero or more chars
    rePat = re.sub(r'\?', '.', rePat)    # one char
    return re.match(rePat, fname)

# a struct to hold the description of one file chunk to copy
@dataclass
class FileChunk:
    ctl_file     : str    # abs path/filename to BACKUP.### file
    bak_file     : str    # abs path/filename to BACKUP.### file
    chunk_offset : int    # byte offset into start of a chunk to copy out
    chunk_size   : int    # chunk size, in bytes
    seq          : int    # chunk sequence number for files which span disks
    complete     : bool   # True if this is the last chunk
    final_size   : int    # expected file size of reconstructed file
    dst_file     : str    # abs path/filename of file being recovered
    date         : bytes  # 4 byte date and time

# =============================================================================
# main routine
# =============================================================================
# The flow is as follows:
#   1. parse command line
#   2. process all control files, reporting errors, and
#      building up a list of actions to take if we need to extract
#   3. filter out any unselected archive files if --wildcard was chosen
#   4. if --list was specified, display them and exit
#   5. scan the list of actions and do error checking
#   6. scan the list of actions and create the target files

##### 1. parse command line #####

parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument('-d', '--debug',
                    action='store_true',
                    help="print out detailed status as the files are processed")
parser.add_argument('-l', '--list',
                    action='store_true',
                    help="only list the files contained in the archive")
parser.add_argument('-c', '--clobber',
                    action='store_true',
                    help='allow extracted files to overwrite existing files')
parser.add_argument('-t', '--timestamp',
                    action='store_true',
                    help='preserve the timestamp on the extacted files')
parser.add_argument('-w', '--wildcard',
                    help='a file name or pattern of which files to extract')
parser.add_argument('infile', nargs='?',  # defaults to None
                    help='name of control file to process, otherwise use all CONTROL.### files')
args = parser.parse_args()

# usually, an entire backup set is processed at once, and the program finds all
# CONTROL.NNN files. But the user may prefer to process backups one control file
# at a time, in which case some of the sanity checks can't be enforced.
# if the user specifies a explict, single control file, assume it is incremental.
incremental = args.infile is not None

##### 2. process all control files #####

# this will be populated with a list of file extractions;
# each entry is a dict for one file or file fragment copy
actions = []

control_files = ()
if incremental:
    control_files = [args.infile]
else:
    # find all CONTROL.### files
    control_files = glob.glob('CONTROL.[0-9][0-9][0-9]')
    control_files.sort()  # paranoia
    # print("Found these control files:", control_files)

seq_num = None  # we expect control files to be numbered 1, 2, 3, etc
for control_fname in control_files:
    if args.debug: print("Processing control file '%s'" % control_fname)
    dir_info = None  # detect if a directory block has been seen yet
    if not os.path.isfile(control_fname):
        print("Error: control file '%s' not found" % control_fname)
        sys.exit()
    with open(control_fname, 'rb') as fh:
        data = fh.read()

    offset = 0   # byte offset into control file

    # the first block must be a header block
    blk_len = data[offset]
    assert blk_len == 0x8b
    header_info = ControlHeader(data[offset : offset+blk_len])
    offset += blk_len
    if seq_num is not None:
        if header_info.seq != seq_num+1:
            print("Error: previous disk seq#=%d; current disk seq#=%d" %
                    (seq_num, header_info.seq))
            sys.exit()
    seq_num = header_info.seq

    # locate the corresponding BACKUP.NNN file
    control_fname = os.path.normcase(os.path.normpath(control_fname))
    head,tail = os.path.split(control_fname)
    backup_fname = os.path.join(head, 'BACKUP.%03d' % header_info.seq)
    if not os.path.isfile(backup_fname):
        print("Error: backup file '%s' not found" % backup_fname)
        sys.exit()
    backup_file_size = os.path.getsize(backup_fname)

    # process the rest of the blocks found in the control file
    while offset < len(data):
        blk_len = data[offset]

        if blk_len == 0x46:
            if (dir_info is not None) and (dir_info.entries > num_files):
                print("Error: expected %d file blocks, found %d" %
                      (dir_info.entries, num_files))
                sys.exit()
            dir_info = ControlDirectory(data[offset : offset+blk_len])
            if args.debug: print("    path: '%s'" % dir_info.path)
            if args.debug: print("    files: %d"  % dir_info.entries)
            num_files = 0  # number of file blocks processed

        elif blk_len == 0x22:
            if dir_info is None:
                print("Error: found file block without dir block at offset %d" % offset)
                sys.exit()
            file_info = ControlFile(data[offset : offset+blk_len])
            if args.debug:
                print("    file='%s', seq=%d, origsize=%d, len=%d, offset=%d, attr=%02x, date=%s" %
                      (file_info.fname, file_info.seq,
                       file_info.final_size, file_info.length,
                       file_info.offset,
                       file_info.attr, file_info.date.as_str))

            # consistency checks
            if (file_info.offset + file_info.length) > backup_file_size:
                print("Error: chunk (%d + %d) extends beyond BACKUP file size %d" %
                        (file_info.offset, file_info.length, backup_file_size))
                sys.exit()

            if file_info.complete and (file_info.seq == 1) and \
               (file_info.length != file_info.final_size):
                print("Error: chunk size %d doesn't match file size %d" %
                      (file_info.length, file_info.final_size))
                sys.exit()

            # save the action to be executed later
            dest_fname = os.path.normpath(dir_info.path + os.sep + file_info.fname)
            action = FileChunk(
                       ctl_file     = control_fname,
                       bak_file     = backup_fname,
                       chunk_offset = file_info.offset,
                       chunk_size   = file_info.length,
                       seq          = file_info.seq,
                       complete     = file_info.complete,
                       final_size   = file_info.final_size,
                       dst_file     = dest_fname,
                       date         = file_info.date
                     )
            actions.append(action)

            num_files += 1
            if num_files > dir_info.entries:
                print("Error: expected %d file blocks, found more" %
                      dir_info.entries)
                sys.exit()

        else:
            print("Error: block len=0x%02x at control file offset %d" %
                  (blk_len, offset))
            sys.exit()

        offset += blk_len

    # done with this control file
    if args.debug: print()

##### 3. filter out any unselected archive files if --wildcard was chosen ####

if args.wildcard:
    filtered = []
    for action in actions:
        head, tail = os.path.split(action.dst_file)
        if globMatch(tail, args.wildcard):
            filtered.append(action)
    actions = filtered

##### 4. if --list was specified, display them and exit #####

if args.list:
    # a file may exist as multiple chunks; report just the first one
    listed = {}
    for action in actions:
        if action.dst_file not in listed:
            listed[action.dst_file] = True
            print("{} {:12,} {}".format(action.date.as_str, action.final_size, action.dst_file))
    sys.exit()

##### 5. scan the list of actions and do error checking #####

@dataclass
class fileProgress:
    dst_file      : str     # path/filename being created
    complete      : bool    # do we think we are done with it
    bytes_written : int     # how many byte written so far
    seq           : int     # sequence number of most recent chunk

# used for sanity checking
target_state = {}

for action in actions:
    if action.dst_file not in target_state:
        # first time we've seen this target file
        if not incremental and (action.seq != 1):
            print("Error: first chunk of %s appears in %s with seq=%d" %
                  (action.dst_file, action.ctl_file, action.seq))
            sys.exit(1)
        dst_file_exists = os.path.isfile(action.dst_file)
        if (action.seq == 1) and dst_file_exists and not args.clobber:
            print("Error: can't clobber existing file %s" % action.dst_file)
            print("Use command argument --clobber to override this")
            sys.exit(1)
        if (action.seq > 1) and not dst_file_exists:
            print("Error: need to append chunk to non-existing file %s" % action.dst_file)
            sys.exit(1)
        target_state[action.dst_file] = \
            fileProgress(
                dst_file      = action.dst_file,
                complete      = action.complete,
                bytes_written = action.chunk_size,
                seq           = action.seq
            )
    else:
        # add another chunk to the target file
        old_state = target_state[action.dst_file]
        if old_state.complete:
            print("Error: control file %s attempted to add another chunk to complete file %s" %
                  (action.ctl_file, action.dst_file))
            sys.exit(1)

        if action.seq != old_state.seq + 1:
            print("Error: chunk #%d of %s was followed by chunk #%d" %
                  (old_state.seq, action.dst_file, action.seq))
            sys.exit(1)

        old_state.seq            = action.seq
        old_state.bytes_written += action.chunk_size
        old_state.complete       = action.complete

        if action.complete and (old_state.bytes_written != action.final_size):
            print("Error: %s was expected to be %d bytes long, but is actually %d" %
                  (action.dst_file, action.final_size, old_state.bytes_written))
            sys.exit(1)

# all control chunks have been processed. now sweep through the target_state
# dict and double check that all files were completed
if not incremental:
    for dst in (target_state.keys()):
        if not target_state[dst].complete:
            print("Warning: not all chunks of file %s were specified" %
                  target_state[dst].dst_file)

##### 6. scan the list of actions and create the target files #####

for action in actions:
    # read the specified chunk from the BACKUP.NNN file
    with open(action.bak_file, 'rb') as fh:
        fh.seek(action.chunk_offset)
        chunk = fh.read(action.chunk_size)
    # create subdirectories, if necessary
    head, tail = os.path.split(action.dst_file)
    if head != '':
        Path(head).mkdir(parents=True, exist_ok=True)
    # write the chunk to the target
    mode = 'wb' if (action.seq == 1) else 'ab'
    with open(action.dst_file, mode) as fh:
        fh.write(chunk)
    if args.timestamp:
        # change the file modification date
        date = datetime.datetime(
            year   = action.date.doy_year,
            month  = action.date.doy_month,
            day    = action.date.doy_day,
            hour   = action.date.tod_hours,
            minute = action.date.tod_minutes,
            second = action.date.tod_seconds)
        modTime = time.mktime(date.timetuple())
        os.utime(action.dst_file, (modTime, modTime))
