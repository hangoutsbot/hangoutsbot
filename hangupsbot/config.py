import collections, functools, json


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
        self.changed = False

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
        return functools.reduce(lambda d, k: d[k], keys_list, self)

    def set_by_path(self, keys_list, value):
        """Set item in config by path (list of keys)"""
        self.get_by_path(keys_list[:-1])[keys_list[-1]] = value

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
