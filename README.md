desktopfs
=========

FUSE filesystem presenting FreeDesktop.org .desktop files in directory structure

Author: Nick Booker

License: MIT

A simple FUSE filesystem that mimics the Applications menu structure.

Example

```

$ sudo apt-get install python-fuse python-xdg
$ mkdir mnt
$ ./desktopfs.py mnt
$ ls mnt
Applications
$ ls mnt/Applications
Accessories  Internet  Programming    System Tools
Graphics     Office    Sound & Video  Zero Install
$ ls mnt/Applications/Accessories
engrampa.desktop     mate-screenshot.desktop   pluma.desktop
gnome-disks.desktop  mate-search-tool.desktop  tomboy.desktop
gucharmap.desktop    mate-terminal.desktop     xfprint.desktop
gvim.desktop         mintstick.desktop         xfprint-manager.desktop
mate-calc.desktop    nautilus.desktop          yelp.desktop
```

You probably want to point nautilus or caja at the mount point though
in order to actually launch the applications.

```
$ caja mnt/Applications/Accessories
```

then double-click one of the entries, or drag and drop a file onto an entry

To unmount:

```
$ fusermount -u mnt
```
