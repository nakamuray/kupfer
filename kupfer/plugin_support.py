import gobject

try:
	import keyring
except ImportError:
	keyring = None


from kupfer import pretty
from kupfer import config
from kupfer.core import settings

__all__ = [
	"UserNamePassword",
	"PluginSettings",
	"check_dbus_connection",
]

def _is_core_setting(key):
	return key.startswith("kupfer_")

class PluginSettings (gobject.GObject, pretty.OutputMixin):
	"""Allows plugins to have preferences by assigning an instance
	of this class to the plugin's __kupfer_settings__ attribute.

	Setting values are accessed by the getitem operator [] with
	the setting's 'key' attribute

	Signals:

		plugin-setting-changed: key, value

	"""
	__gtype_name__ = "PluginSettings"

	def __init__(self, *setdescs):
		"""Create a settings collection by passing in dictionaries
		as arguments, where each dictionary must have the following keys:
			key
			type
			value (default value)
			label (localized label)

		the @key may be any string except strings starting with
		'kupfer_', which are reserved
		"""
		gobject.GObject.__init__(self)
		self.setting_descriptions = {}
		self.setting_key_order = []
		req_keys = set(("key", "value", "type", "label"))
		for desc in setdescs:
			if not req_keys.issubset(desc.keys()):
				missing = req_keys.difference(desc.keys())
				raise KeyError("Plugin setting missing keys: %s" % missing)
			self.setting_descriptions[desc["key"]] = dict(desc)
			self.setting_key_order.append(desc["key"])

	def __iter__(self):
		return iter(self.setting_key_order)

	def initialize(self, plugin_name):
		"""Init by reading from global settings and setting up callbacks"""
		setctl = settings.GetSettingsController()
		for key in self:
			value_type = self.setting_descriptions[key]["type"]
			value = setctl.get_plugin_config(plugin_name, key, value_type)
			if value is not None:
				self[key] = value
			elif _is_core_setting(key):
				default = self.setting_descriptions[key]["value"]
				setctl.set_plugin_config(plugin_name, key, default, value_type)
		setctl.connect("value-changed", self._value_changed, plugin_name)

	def __getitem__(self, key):
		return self.setting_descriptions[key]["value"]
	def __setitem__(self, key, value):
		value_type = self.setting_descriptions[key]["type"]
		self.setting_descriptions[key]["value"] = value_type(value)
		if not _is_core_setting(key):
			self.emit("plugin-setting-changed", key, value)

	def _value_changed(self, setctl, section, key, value, plugin_name):
		"""Preferences changed, update object"""
		if key in self and plugin_name in section:
			self[key] = value

	def get_value_type(self, key):
		"""Return type of setting @key"""
		return self.setting_descriptions[key]["type"]
	def get_label(self, key):
		"""Return label for setting @key"""
		return self.setting_descriptions[key]["label"]
	def get_alternatives(self, key):
		"""Return alternatives for setting @key (if any)"""
		return self.setting_descriptions[key].get("alternatives")
	def get_tooltip(self, key):
		"""Return tooltip string for setting @key (if any)"""
		return self.setting_descriptions[key].get("tooltip")

	def connect_settings_changed_cb(self, callback, *args):
		self.connect("plugin-setting-changed", callback, *args)


# Signature: Key, Value
gobject.signal_new("plugin-setting-changed", PluginSettings,
		gobject.SIGNAL_RUN_LAST, gobject.TYPE_BOOLEAN,
		(gobject.TYPE_STRING, gobject.TYPE_PYOBJECT))

# Plugin convenience functions for dependencies

_has_dbus_connection = None

def check_dbus_connection():
	"""
	Check if a connection to the D-Bus daemon is available,
	else raise ImportError with an explanatory error message.

	For plugins that can not be used without contact with D-Bus;
	if this check is used, the plugin may use D-Bus and assume it
	is available in the Plugin's code.
	"""
	global _has_dbus_connection
	if _has_dbus_connection is None:
		import dbus
		try:
			dbus.Bus()
			_has_dbus_connection = True
		except dbus.DBusException, err:
			_has_dbus_connection = False
	if not _has_dbus_connection:
		raise ImportError(_("No D-Bus connection to desktop session"))

def check_keyring_support():
	"""
	Check if the UserNamePassword class can be used,
	else raise ImportError with an explanatory error message.
	"""
	import keyring

class UserNamePassword (settings.ExtendedSetting):
	''' Configuration type for storing username/password values.
	Username is stored in Kupfer config, password in keyring '''
	def __init__(self, obj=None):
		settings.ExtendedSetting.__init__(self)
		self._configure_keyring()
		self.username = None
		self.password = None
		if obj:
			self.username = obj.username
			self.password = obj.password

	def __repr__(self):
		return '<UserNamePassword "%s", %s>' % (self.username,
		                                        bool(self.password))

	@classmethod
	def _configure_keyring(cls):
		# Configure the fallback keyring's configuration file if used
		import keyring.backend
		kr = keyring.get_keyring()
		if hasattr(kr, "crypted_password"):
			keyring.set_keyring(keyring.backend.UncryptedFileKeyring())
			kr = keyring.get_keyring()
		if hasattr(kr, "file_path"):
			kr.file_path = config.save_config_file("keyring.cfg")

	def load(self, plugin_id, key, username):
		self.password = keyring.get_password(plugin_id, username)
		self.username = username

	def save(self, plugin_id, key):
		''' save @user_password - store password in keyring and return username
		to save in standard configuration file '''
		keyring.set_password(plugin_id, self.username, self.password)
		return self.username

if not keyring:
	class UserNamePassword (object):
		pass

