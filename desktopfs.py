#!/usr/bin/python -S
# -*- coding: utf-8 -*-

import sys
sys.setdefaultencoding('utf-8')
import site

import errno  
import fuse  
import stat  
import time
import os
import xdg.Menu
try:
    import cStringIO as stringio
except ImportError:
    try:
        import StringIO as stringio
    except ImportError:
        import stringio
  
fuse.fuse_python_api = (0, 2)

def path_parts(path):
    """Split path into list of parts, starting from '/'"""
    parts = []
    dirname = path
    basename = 'X'
    while basename:
        dirname, basename = os.path.split(dirname)
        if basename:
            parts.insert(0, basename)
    return parts

class Entity(object):
    def __init__(self, name):
        self._name = name
        self._perms = self.default_perms()

    def default_perms(self):
        return 0644

    def get_name(self):
        return self._name

    def stat_type(self):
        raise NotImplementedError()

    def stat_perms(self):
        return self._perms

    def chmod(self, perms):
        self._perms = perms

    def stat(self):
        stat_ft = self.stat_type()
        st = fuse.Stat()
        st.st_mode = stat_ft | self.stat_perms()
        st.st_nlink = self.nlink()
        st.st_atime = int(time.time())  
        st.st_mtime = st.st_atime  
        st.st_ctime = st.st_atime
        size = self.size()
        if size is not None:
            st.st_size = size
        return st

    def nlink(self):
        return 1

    def subentries(self):
        """Most types of file have no subentries"""
        return {}

    def get_path(self, path):
        """Get the entity at the given path relative to this entity."""
        parts = path_parts(path)
        entry = self
        while parts:
            try:
                part = parts.pop(0) # remove first element
            except IndexError:
                break
            entries = entry.subentries()
            entry = entries.get(part)
            if not entry:
                return None
        if parts:
            return None
        return entry

    def open(self, flags):
        raise NotImplementedError("open() not implemented for this entity")

    def read(self, size, offset):
        """Read part of this entity."""
        raise NotImplementedError("read() not implemented for this entity")

    def size(self):
        """Override if it has a size"""
        return None

class Directory(Entity):
    def stat_type(self):
        return stat.S_IFDIR

    def nlink(self):
        return len(self.subdir_names())

    def default_perms(self):
        return 0755

    def subentries(self):
        entities = self._get_subentry_entities()
        return dict((o.get_name(), o) for o in entities)

    def subdir_names(self):
        names = ['.', '..']
        return names + self.subentries().keys()

    def _get_subentry_entities(self):
        """Override this.  Return iterable over Entity objects

        Your directory will always be empty otherwise.
        """
        return []

class RegularFile(Entity):
    def size(self):
        return len(self.content)

    def stat_type(self):
        return stat.S_IFREG

    @property
    def content(self):
        raise NotImplementedError()


class RegularFileFixedContent(RegularFile):
    def _get_content(self):
        if not hasattr(self, '_content'):
            self._content = ''
        return self._content

    def _set_content(self, value):
        self._content = value

    content = property(_get_content, _set_content)

    def open(self, flags):
        # only support 'READ ONLY'
        access_flags = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & access_flags) != os.O_RDONLY:
            return -errno.EACCES
        else:
            return 0

    def read(self, size, offset):
        if offset < self.size():
            fakefile = stringio.StringIO(self.content)
            fakefile.seek(offset)
            read_string = fakefile.read(size)
            return read_string
        else:
            return ''

    content = property(_get_content, _set_content)

class RootDir(Directory):
    rootmenu = xdg.Menu.parse()
    def _get_subentry_entities(self):
        appsdir = XDGMenuDir(name='Applications')
        appsdir.set_menu(self.__class__.rootmenu)
        yield appsdir

class XDGMenuDir(Directory):
    def set_menu(self, xdg_menu):
        self._menu = xdg_menu

    def _get_subentry_entities(self):
        for entry in self._menu.getEntries():
            if isinstance(entry, xdg.Menu.Menu):
                directory = XDGMenuDir(name=str(entry.getName()))
                directory.set_menu(entry)
                yield directory
            elif isinstance(entry, xdg.Menu.MenuEntry):
                desktop_entry = entry.DesktopEntry
                filename = os.path.basename(desktop_entry.filename)
                thefile = RegularFileFixedContent(name=filename)
                thefile.chmod(0755)
                thefile.content = file(desktop_entry.filename, 'r').read()
                yield thefile
  
class DesktopFS(fuse.Fuse):  
    def __init__(self, *args, **kw):  
        fuse.Fuse.__init__(self, *args, **kw)
        self.root = RootDir(name='/')
  
    def getattr(self, path):
        entry = self._find_directory_entry(path)
        if not entry:
            return -errno.ENOENT
        return entry.stat()  

    def readdir(self, path, offset):
        entry = self._find_directory_entry(path)
        if not entry:
            #print >>sys.stderr, "-> path not found"
            return
        for name in entry.subdir_names():
            yield fuse.Direntry(name)

    def open(self, path, flags):
        entry = self._find_directory_entry(path)
        return entry.open(flags)

    def read(self, path, size, offset):
        entry = self._find_directory_entry(path)
        return entry.read(size, offset)

    def _find_directory_entry(self, path):
        return self.root.get_path(path)

            
if __name__ == '__main__':  
    fs = DesktopFS()  
    fs.parse(errex=1)  
    fs.main()
