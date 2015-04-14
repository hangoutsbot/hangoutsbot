import collections
import functools
import json
import sys

class Config(collections.MutableMapping):
    """Configuration JSON storage class"""
    def __init__(self, filename, default=None):
        self.filename = filename
        self.default = None
        self.config = {}
        self.changed = False
        self.load()

    def load(self):
        """Load config from file"""
        try:
            self.config = json.load(open(self.filename))
        except IOError:
            self.config = {}
        except ValueError:
            # better error-handling for n00bs, including me!
            print(_("exception occurred, config.json likely malformed"))
            print(_("  check {}").format(self.filename))
            print(_("  {}").format(sys.exc_info()[1]))
            sys.exit(0)

        self.changed = False

    def force_taint(self):
        self.changed = True

    def loads(self, json_str):
        """Load config from JSON string"""
        self.config = json.loads(json_str)
        self.changed = True

    def save(self):
        """Save config to file (only if config has changed)"""
        if self.changed:
            with open(self.filename, 'w') as f:
                json.dump(self.config, f, indent=2, sort_keys=True)
                self.changed = False

    def get_by_path(self, keys_list):
        """Get item from config by path (list of keys)"""
        return functools.reduce(lambda d, k: d[int(k) if isinstance(d, list) else k], keys_list, self)

    def set_by_path(self, keys_list, value):
        """Set item in config by path (list of keys)"""
        self.get_by_path(keys_list[:-1])[keys_list[-1]] = value
        self.changed = True

    def pop_by_path(self, keys_list):
        popped_value = self.get_by_path(keys_list[:-1]).pop(keys_list[-1])
        self.changed = True
        return popped_value

    def get_option(self, keyname):
        try:
            value = self.config[keyname]
        except KeyError:
            value = None
        return value

    def get_suboption(self, grouping, groupname, keyname):
        try:
            value = self.config[grouping][groupname][keyname]
        except KeyError:
            value = self.get_option(keyname)
        return value

    def exists(self, keys_list):
        _exists = True

        try:
            if self.get_by_path(keys_list) is None:
                _exists = False
        except (KeyError, TypeError):
            _exists = False

        return _exists

    def __getitem__(self, key):
        try:
            return self.config[key]
        except KeyError:
            return self.default

    def __setitem__(self, key, value):
        self.config[key] = value
        self.changed = True

    def __delitem__(self, key):
        del self.config[key]
        self.changed = True

    def __iter__(self):
        return iter(self.config)

    def __len__(self):
        return len(self.config)
