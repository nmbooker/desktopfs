#!/usr/bin/python -S
# -*- coding: utf-8 -*-

"""A FUSE filesystem to show the XDG menu structure in your file browser.

Currently read-only and only working for the Applications subtree.

Copyright (C) Nicholas Booker <NMBooker@gmail.com>

License: MIT
"""

# Hack to make xdg.Menu.parse work properly
# hack also consists of the '#!/usr/bin/python -S' line up top
import sys
sys.setdefaultencoding('utf-8')
import site
# End of hack to make xdg.Menu.parse work properly

import sys
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

### GENERIC FILESYSTEM REPRESENTATION
class Entity(object):
    """Base Entity object, should be treated as abstract.

    Represents an entity on your filesystem.

    An entity could be a RegularFile, a Directory, etc.

    Imagine a tree of objects, each a subclass of Entity.
    The root will typically be a Directory, but then any other Entity will
    do below that as long as the usual Unix filesystem rules are adhered to.

    root=Directory(name='/')
    |- Directory(name='usr')
    |- RegularFile(name='hello.txt')

    If developing a new kind of entity, subclass this and implement methods marked ABSTRACT
    in their docstring.
    The ones that are implemented here but you're most likely to want to override are
    hinted as such in the docstrings.
    """
    def __init__(self, name):
        self._name = name
        self._perms = self.default_perms()

    def default_perms(self):
        """The default initial permissions bitmap for an entity of this type.

        This implementation defaults to 0644, which means rw-r--r--

        You might want to override this for certain types if this isn't appropriate
        (Directories for example)
        """
        return 0644

    def get_name(self):
        """Return the filename of this entity.

        No path information is provided, it's assumed you know where in the tree this
        is.
        """
        return self._name

    def stat_type(self):
        """ABSTRACT: return the stat.S_IF* constant representing the type of entity"""
        raise NotImplementedError()

    def stat_perms(self):
        """Return the permissions bitmap for this entity."""
        return self._perms

    def chmod(self, perms):
        """Change the permissions bitmap for this entity instance."""
        self._perms = perms

    def stat(self):
        """Return the fuse.Stat() structure for this entity.
        """
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
        """Return the number of links.

        Assumed to be 1 for most types of entity, but you might want to override this.
        """
        return 1

    def subentries(self):
        """Return a dictionary of Entities that are direct children of this Entity.

        The values should be Entities.
        Each key should be the name attribute of that entity.

        Override this if you're representing a Unix directory (unless you want
        your directory to always empty that is!)
        """
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
        """Open this entity with the given flags.

        Override this for non-directory files.
        """
        raise NotImplementedError("open() not implemented for this entity")

    def read(self, size, offset):
        """Read part of this entity.

        Override this for non-directory files.
        """
        raise NotImplementedError("read() not implemented for this entity")

    def size(self):
        """Size of your entity as integer in bytes.

        Override this if your entity has a size (if not a directory, it probably has)

        If None is returned, stat() will assume it to be undefined and the Stat()
        object returned will take the default value of st_size
        """
        return None

class Directory(Entity):
    def stat_type(self):
        """The type of entity as known by stat().

        It's stat.S_IFDIR because this is a directory.
        """
        return stat.S_IFDIR

    def nlink(self):
        """Return the number of links to this directory.
        """
        return len(self.subdir_names())

    def default_perms(self):
        """Set the default initial permissions for a directory.

        These can be overridden after instantiation with self.chmod(mode)
        """
        return 0755

    def subentries(self):
        """Get the files in this directory (except for the implicit . and ..)

        Override _get_subentry_entities() to affect the output of this.
        """
        entities = self._get_subentry_entities()
        return dict((o.get_name(), o) for o in entities)

    def subdir_names(self):
        """Get the names of the children of this directory
        (. and .. are included automatically)

        This depends on the result of subentries().
        """
        names = ['.', '..']
        return names + self.subentries().keys()

    def _get_subentry_entities(self):
        """Return iterable over Entity objects.

        The 'name' of each one is used by subentries() to get the keys for the
        dictionary.

        You should override this, or your directory will always be empty otherwise.
        """
        return []

class RegularFile(Entity):
    """Base class for representing a regular file.  Should be treated as abstract.
    """
    def size(self):
        return len(self.content)

    def stat_type(self):
        return stat.S_IFREG

    @property
    def content(self):
        raise NotImplementedError()


class RegularFileFixedContent(RegularFile):
    """Read-only Regular file backed by a string set in attribute '.content'

    myfile = RegularFileFixedContent(name='hello.txt')
    myfile.content = 'hello\\n'
    """
    def _get_content(self):
        if not hasattr(self, '_content'):
            self._content = ''
        return self._content

    def _set_content(self, value):
        self._content = value

    content = property(_get_content, _set_content)

    def open(self, flags):
        """Open this file with given flags.

        Only O_RDONLY is supported for this file type at the moment.
        Any other will cause -errno.EACCES to be returned.

        0 indicates success.
        """
        # only support 'READ ONLY'
        access_flags = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & access_flags) != os.O_RDONLY:
            return -errno.EACCES
        else:
            return 0

    def read(self, size, offset):
        """Read 'size' bytes of this file from byte 'offset'

        Always returns a byte string. (str)
        """
        if offset < self.size():
            fakefile = stringio.StringIO(self.content)
            fakefile.seek(offset)
            read_string = fakefile.read(size)
            return read_string
        else:
            return ''

### desktopfs-specific Entity objects start here
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

### This is the FUSE filesystem itself.
class DesktopFS(fuse.Fuse): 
    """The DesktopFS FUSE filesystem.

    The filesystem is currently read-only, so only getattr(), readdir(), open() and read()
    are implemented.

    The API I'm implementing is described here:
    http://sourceforge.net/apps/mediawiki/fuse/index.php?title=SimpleFilesystemHowto

    fs = DesktopFS()
    fs.parse(errex=1)
    fs.main()
    """
    def __init__(self, *args, **kw):  
        fuse.Fuse.__init__(self, *args, **kw)
        # This hooks up our filesystem root directory.
        self.root = RootDir(name='/')
  
    # This stuff is actually quite generic, and would work if
    # I hooked up any other Directory instance to self.root in __init__
    # Perhaps this warrants extraction into a module?
    def getattr(self, path):
        """Return a fuse.Stat() instance representing the entity at the given path

        On failure, return an appropriate constant from errno, e.g. -errno.ENOENT
        """
        entry = self._find_directory_entry(path)
        if not entry:
            return -errno.ENOENT
        return entry.stat()  

    def readdir(self, path, offset):
        """Return a (possibly empty) generator of directory entries in the
        given directory.
        """
        entry = self._find_directory_entry(path)
        if not entry:
            return
        for name in entry.subdir_names():
            yield fuse.Direntry(name)

    def open(self, path, flags):
        """Open the path with flags, returning 0 on success or -errno on failure.
        """
        entry = self._find_directory_entry(path)
        return entry.open(flags)

    def read(self, path, size, offset):
        """Read from the file.  Return the resulting string.
        """
        entry = self._find_directory_entry(path)
        return entry.read(size, offset)

    def _find_directory_entry(self, path):
        """Find the Entity at the given path relative to the entity at self.root
        """
        return self.root.get_path(path)

            
if __name__ == '__main__':  
    fs = DesktopFS()  
    fs.parse(errex=1)  
    fs.main()
