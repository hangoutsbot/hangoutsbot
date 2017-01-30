import collections, datetime, functools, json, glob, logging, os, shutil, sys, time

from threading import Timer


logger = logging.getLogger(__name__)


class Config(collections.MutableMapping):
    """Configuration JSON storage class"""
    def __init__(self, filename, default=None, failsafe_backups=0, save_delay=0):
        self.filename = filename
        self.default = None
        self.config = {}
        self.changed = False
        self.failsafe_backups = failsafe_backups
        self.save_delay = save_delay
        self.load()

        self._timer_save = False

    def _make_failsafe_backup(self):
        try:
            with open(self.filename) as f:
                json.load(f)
        except IOError:
            return False
        except ValueError:
            logger.warning("{} is corrupted, aborting backup".format(self.filename))
            return False

        existing = sorted(glob.glob(self.filename + ".*.bak"))
        while len(existing) > (self.failsafe_backups - 1):
            os.remove(existing.pop(0))

        backup_file = self.filename + "." + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + ".bak"
        shutil.copy2(self.filename, backup_file)

        return True

    def _recover_from_failsafe(self):
        existing = sorted(glob.glob(self.filename + ".*.bak"))
        while len(existing) > 0:
            try:
                recovery_filename = existing.pop()
                with open(recovery_filename) as f:
                    # test the file is valid json
                    json.load(f)

                shutil.copy2(recovery_filename, self.filename)
                self.load(recovery=True)
                logger.info("recovery successful: {}".format(recovery_filename))
                return True
            except IOError:
                pass
            except ValueError:
                logger.error("corrupted recovery: {}".format(self.filename))
        return False

    def load(self, recovery=False):
        """Load config from file"""
        try:
            with open(self.filename) as f:
                self.config = json.load(f)
            logger.info("{} read".format(self.filename))

        except IOError:
            self.config = {}

        except ValueError:
            if not recovery and self.failsafe_backups > 0 and self._recover_from_failsafe():
                return

            raise

        self.changed = False

    def force_taint(self):
        self.changed = True

    def loads(self, json_str):
        """Load config from JSON string"""
        self.config = json.loads(json_str)
        self.changed = True

    def save(self, delay=True):
        if self.save_delay:
            if delay:
                if self._timer_save and self._timer_save.is_alive():
                    self._timer_save.cancel()
                self._timer_save = Timer(self.save_delay, self.save, [], {"delay": False})
                self._timer_save.start()
                return False

        """Save config to file (only if config has changed)"""
        if self.changed:
            start_time = time.time()

            if self.failsafe_backups:
                self._make_failsafe_backup()

            with open(self.filename, 'w') as f:
                json.dump(self.config, f, indent=2, sort_keys=True)
                self.changed = False
            interval = time.time() - start_time

            logger.info("{} write {}".format(self.filename, interval))

        return self.changed

    def flush(self):
        if self._timer_save and self._timer_save.is_alive():
            logger.info("flushing {}".format(self.filename))
            self._timer_save.cancel()
        self.save(delay=False)

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
