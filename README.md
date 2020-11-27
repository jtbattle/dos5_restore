dos5_restore.py
===============
This utility script allows displaying and extracting files from backup archives
made via the DOS BACKUP.EXE utility. In a DOS environment, RESTORE.EXE is
used for this purpose, but it didn't work for me, so I wrote this instead.

Apparently the file format created by BACKUP.EXE changed between DOS 3.2 and
DOS 3.3, then again for DOS 6.0. This utility handles only only archives
made starting with DOS 3.3 and before DOS 6.0.

Warning: I have used it only on two archives, so it is likely that faced with
more real-world examples, it may expose shortcomings.

In my particular case, I had captured a set of 5.25 inch floppy disks via
the [Kryoflux floppy interface card](https://www.kryoflux.com/), which
resulted in a set of virtual disk images, eg disk1.img, disk2.img, etc.
The contents of these virtual disk images can be accessed via the
[WinImage](http://www.winimage.com/winimage.htm) utility; this program
understands the FAT file system and can display and extract the DOS files
to the host file system.

These virutal disk images can also be mounted as virtual floppy disks in the
[DOSBOX](https://www.dosbox.com/) emulator. From there it is possible to
run RESTORE.EXE, but recovery of the full archive requires swapping the
virtual floppy disk which is mounted (in my case, about a dozen times)
while RESTORE.EXE is running. This hitch is that DOSBOX requires running
DOS command-line utilities to mount (imgmount) and unmount (mount -u) to
perform the swap.

My solution was to extract all the CONTROL.### and BACKUP.### files from
the dozen kryoflux .img files all in one directory. From there, the python
utility I wrote, dos5_restore.py, will read all the control files, check
everything for consistency, then list or extract the archive.

Command Help
------------
    usage: dos5_restore.py [-h] [-d] [-l] [-c] [-t] [-w WILDCARD] [infile]

    positional arguments:
      infile                name of control file to process, otherwise use all CONTROL.### files

    optional arguments:
      -h, --help            show this help message and exit
      -d, --debug           print out detailed status as the files are processed
      -l, --list            only list the files contained in the archive
      -c, --clobber         allow extracted files to overwrite existing files
      -t, --timestamp       preserve the timestamp on the extacted files
      -w WILDCARD, --wildcard WILDCARD
                            a file name or pattern of which files to extract

The wildcard patterns are typical DOS file patterns:
* asterisk means zero or more of any characters
* question mark means one of any character

License
--------------
This code is released under the [MIT License](https://mit-license.org/)

Copyright © 2020 Jim Battle

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the “Software”), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

