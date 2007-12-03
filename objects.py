# -*- coding: UTF-8 -*-

import gobject
import gnomevfs
import itertools
from os import path

import utils

class Error (Exception):
	pass

class NoParent (Error):
	pass

class NoContent (Error):
	pass

class NoApplication (Error):
	pass


class KupferObject (object):
	"""
	Base class for Actions and Leaves
	"""
	icon_size = 96
	def __init__(self, name):
		self.name = name
	
	def __repr__(self):
		return "<%s %s at %x>" % (self.__class__.__name__, str(self), id(self))
	
	def __str__(self):
		return self.name

	def get_pixbuf(self):
		return None

def aslist(seq):
	if not isinstance(seq, type([])) and not isinstance(seq, type(())):
		seq = list(seq)
	return seq

class Source (KupferObject):
	"""
	Source: Data provider for a kupfer browser
	"""
	def __init__(self, name=None):
		if not name:
			name = self.__class__.__name__
		KupferObject.__init__(self, name)
		self.cached_items = None

	def set_refresh_callback(self, refresh_callback):
		"""
		Set function to be called on owner when data needs refresh
		"""
		self.refresh_callback = refresh_callback

	def get_items(self):
		"""
		Internal method to compute and return the needed items
		
		This _must_ return a list and not an iterator if
		the source is not dynamic
		"""
		return []

	def is_dynamic(self):
		"""
		Whether to recompute contents each time it is accessed
		"""
		return False

	def get_leaves(self):
		"""
		Return a list of all leaves
		"""
		if not self.cached_items or self.is_dynamic():
			self.cached_items = aslist(self.get_items())
		return self.cached_items

	def has_parent(self):
		return False

	def get_parent(self):
		raise NoParent

	def representation(self):
		"""
		Return represented object
		"""
		return self

class Leaf (KupferObject):
	def __init__(self, obj, value):
		super(Leaf, self).__init__(value)
		self.object = obj
		self.value = value
	
	def has_content(self):
		return False
	
	def content_source(self):
		raise NoContent

	def get_actions(self):
		return ()


class FileLeaf (Leaf):
	def _desktop_item(self, basename):
		from gnomedesktop import item_new_from_basename, LOAD_ONLY_IF_EXISTS
		return item_new_from_basename(basename, LOAD_ONLY_IF_EXISTS)

	def get_actions(self):
		acts = [Echo(), Dragbox()]
		default = None
		if path.isdir(self.object):
			acts.extend([OpenTerminal()])
			default = Show(name="Open")
		else:
			type = gnomevfs.get_mime_type(self.object)
			def_app = gnomevfs.mime_get_default_application(type)
			types = gnomevfs.mime_get_all_applications(type)
			apps = set()
			if def_app:
				default = OpenWith(self._desktop_item(def_app[0]), def_app[1])
				apps.add(def_app[1])
			for info in types:
				id = info[1]
				if id not in apps:
					acts.append(OpenWith(self._desktop_item(info[0]), info[1]))
					apps.add(id)
		if not default:
			default = Show()
		acts.insert(0, default)
		return acts

	def has_content(self):
		return path.isdir(self.object)

	def content_source(self):
		if self.has_content():
			return DirectorySource(self.object)
		else:
			return Leaf.content_source(self)

	def get_pixbuf(self):
		uri = gnomevfs.get_uri_from_local_path(self.object)
		icon = utils.get_icon_for_uri(uri, self.icon_size)
		return icon

class SourceLeaf (Leaf):
	def has_content(self):
		return True

	def content_source(self):
		return self.object


class Action (KupferObject):
	def activate(self, leaf):
		pass
	
	def activate_many(self, leaves):
		pass
	
	def get_pixbuf(self):
		return utils.get_icon_for_name("utilities-terminal", self.icon_size)


class Echo (Action):
	def __init__(self):
		super(Echo, self).__init__("Echo")
	
	def activate(self, leaf):
		print "Echo:", leaf.object

class OpenWith (Action):
	"""
	Open a FileLeaf with a specified application
	"""

	def __init__(self, desktop_item, name):
		Action.__init__(self, name)
		self.desktop_item = desktop_item
	
	def activate(self, leaf):
		filepath = leaf.object
		self.desktop_item.launch([filepath], 0)
	
	def get_pixbuf(self):
		uri = self.desktop_item.get_location()
		file = gnomevfs.get_local_path_from_uri(uri)
		app_icon = utils.get_desktop_icon(path.basename(file), self.icon_size)
		if not app_icon:
			app_icon = utils.get_default_application_icon(self.icon_size)
		return app_icon


class Show (Action):
	def __init__(self, name=None):
		"""
		Open file with default viewer
		"""
		if not name:
			name = "Show"
		super(Show, self).__init__(name)
	
	def activate(self, leaf):
		print "Show: %s" % (leaf.object,)
		uri = gnomevfs.get_uri_from_local_path(leaf.object)
		gnomevfs.url_show(uri)
	
	def get_pixbuf(self):
		return utils.get_default_application_icon(self.icon_size)

class OpenTerminal (Action):
	def __init__(self):
		super(OpenTerminal, self).__init__("Open Terminal here")
	
	def activate(self, leaf):
		argv = ["gnome-terminal"]
		print argv
		utils.spawn_async(argv, in_dir=leaf.object)


class Dragbox (Action):
	def __init__(self):
		super(Dragbox, self).__init__("Put on dragbox")
	
	def activate(self, leaf):
		path = leaf.object
		argv = ["dragbox", "--file", path]
		gobject.spawn_async(argv, flags=gobject.SPAWN_SEARCH_PATH)


class FileSource (Source):
	def __init__(self, dirlist, depth=0):
		super(FileSource, self).__init__()
		self.dirlist = dirlist
		self.depth = depth

	def get_items(self):
		iters = []
		
		def mkleaves(dir):
			files = utils.get_dirlist(dir, depth=self.depth, exclude=self._exclude_file)
			return (FileLeaf(f, path.basename(f)) for f in files)

		for d in self.dirlist:
			iters.append(mkleaves(d))

		return itertools.chain(*iters)

	def _exclude_file(self, filename):
		return filename.startswith(".") 

class DirectorySource (Source):
	def __init__(self, dir):
		super(DirectorySource, self).__init__()
		self.directory = dir
		self.deep = False

	def get_items(self):
		dirlist = utils.get_dirlist(self.directory, exclude=lambda f: f.startswith("."))
		def file_leaves(files):
			for file in files:
				basename = path.basename(file)
				if path.isdir(file):
					basename += "/"
				yield FileLeaf(file, basename)

		return file_leaves(dirlist)

	def _parent_path(self):
		return path.normpath(path.join(self.directory, path.pardir))

	def has_parent(self):
		return self.directory != self._parent_path()

	def get_parent(self):
		if not self.has_parent():
			return FileSource.has_parent(self)
		return DirectorySource(self._parent_path())


class SourcesSource (Source):
	def __init__(self, sources):
		super(SourcesSource, self).__init__()
		self.sources = sources
	
	def get_items(self):
		return (SourceLeaf(s, str(s)) for s in self.sources)

class MultiSource (Source):
	def __init__(self, sources):
		super(MultiSource, self).__init__()
		self.sources = sources

	def get_items(self):
		iterators = []
		for so in self.sources:
			it = so.get_items()
			iterators.append(it)

		return itertools.chain(*iterators)

class Launch (Action):
	"""
	Launches AppLeaf
	"""
	def __init__(self):
		Action.__init__(self, "Launch")
	
	def activate(self, leaf):
		desktop_item = leaf.object
		args = []
		desktop_item.launch(args, 0)
	
	def get_pixbuf(self):
		return utils.get_default_application_icon(self.icon_size)

class AppLeaf (Leaf):
	def __init__(self, item):
		from gnomedesktop import KEY_NAME, KEY_EXEC
		value = "%s (%s)" % (item.get_localestring(KEY_NAME), item.get_string(KEY_NAME))
		Leaf.__init__(self, item, value)
	
	def get_actions(self):
		return (Launch(),)

	def get_pixbuf(self):
		from gtk import icon_theme_get_default
		icon_file = self.object.get_icon(icon_theme_get_default())
		#icon_file = gnomevfs.get_local_path_from_uri(icon_uri)
		if not icon_file:
			return utils.get_default_application_icon(self.icon_size)
		return utils.get_icon_from_file(icon_file, self.icon_size)

class AppSource (Source):

	def __init__(self):
		super(AppSource, self).__init__()

	def get_items(self):
		dirs = utils.get_xdg_data_dirs()
		from os import walk
		from gnomedesktop import item_new_from_file, LOAD_ONLY_IF_EXISTS
		import gnomedesktop as gd

		desktop_files = []

		inc_files = set()

		def add_desktop_item(item):
			# "true" or "false"
			hid = item.get_string(gd.KEY_HIDDEN)
			nodisp = item.get_string(gd.KEY_NO_DISPLAY)
			type = item.get_string(gd.KEY_TYPE)

			if "true" in (hid, nodisp) or (type != "Application"):
				return
			file = gnomevfs.get_local_path_from_uri(item.get_location())
			name = path.basename(file)
			if name in inc_files:
				return
			inc_files.add(name)
			desktop_files.append(item)
		
		for d in dirs:
			apps = path.join(d, "applications")
			if not path.exists(apps):
				continue
			for root, dirnames, fnames in walk(apps):
				for file in fnames:
					abspath = path.join(root, file)
					item = item_new_from_file(abspath, LOAD_ONLY_IF_EXISTS)
					if item:
						add_desktop_item(item)

				del dirnames[:]
		
		return (AppLeaf(item) for item in desktop_files)


