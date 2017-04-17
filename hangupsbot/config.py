import asyncio
import collections
from datetime import datetime
import functools
import json
import glob
import logging
import os
import shutil
import time

logger = logging.getLogger(__name__)


class Config(collections.MutableMapping):
    """Configuration JSON storage class"""
    def __init__(self, filename, default=None, failsafe_backups=0, save_delay=0):
        self.filename = filename
        self.default = default
        self.config = {}
        self.failsafe_backups = failsafe_backups
        self.save_delay = save_delay
        self._last_dump = None
        self._timer_save = None
        self.load()

    @property
    def _changed(self):
        """return weather the config changed since the last dump

        Returns:
            boolean, True if config matches with the last dump, otherwise False
        """
        try:
            current_state = json.dumps(self.config, indent=2, sort_keys=True)
            return current_state != self._last_dump

        except TypeError:
            # currupt config
            return True

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
            path = existing.pop(0)
            try:
                os.remove(path)
            except IOError:
                logger.warning('Failed to remove %s, check permissions', path)

        backup_file = "%s.%s.bak" % (self.filename,
                                     datetime.now().strftime("%Y%m%d%H%M%S"))
        shutil.copy2(self.filename, backup_file)
        return True

    def _recover_from_failsafe(self):
        existing = sorted(glob.glob(self.filename + ".*.bak"))
        recovery_filename = None
        while len(existing) > 0:
            try:
                recovery_filename = existing.pop()
                with open(recovery_filename, 'r') as file:
                    data = file.read()
                self._loads(data)
                self.save(delay=False)
                logger.info("recovered %s successful from %s", self.filename,
                            recovery_filename)
                return True
            except IOError:
                logger.warning('Failed to remove %s, check permissions',
                               recovery_filename)
            except ValueError:
                logger.error("corrupted recovery: {}".format(self.filename))
        return False

    def load(self):
        try:
            with open(self.filename) as file:
                data = file.read()
            self._loads(data)
            self._last_dump = data
            logger.info("%s read", self.filename)

        except IOError:
            if not os.path.isfile(self.filename):
                self.config = {}
                self.save(delay=False)
                return
            raise

        except ValueError:
            if self.failsafe_backups and self._recover_from_failsafe():
                return
            raise

    def _loads(self, json_str):
        """Load config from JSON string

        Args:
            json_str: string, a json formated string that overrides the config

        Raises:
            ValueError: the string is not a valid json representing of a dict
        """
        self.config = json.loads(json_str)

    def save(self, delay=True):
        """dump the cached data to file

        Args:
            delay: boolean, set to False to force an immediate dump

        Raises:
            IOError: the config can not be saved to the configured path
            ValueError: the config can not be formated as json
        """
        if self._timer_save is not None:
            self._timer_save.cancel()

        if self.save_delay and delay:
            self._timer_save = asyncio.get_event_loop().call_later(
                self.save_delay, self.save, False)
            return

        if not self._changed:
            # skip dumping as the file is already up to date
            return

        start_time = time.time()

        if self.failsafe_backups:
            self._make_failsafe_backup()

        self._last_dump = json.dumps(self.config, indent=2, sort_keys=True)
        with open(self.filename, 'w') as file:
            file.write(self._last_dump)

        interval = time.time() - start_time
        logger.info("%s write %s", self.filename, interval)

    def flush(self):
        logger.info("flushing %s", self.filename)
        self.save(delay=False)

    def get_by_path(self, keys_list):
        """Get item from config by path (list of keys)"""
        return functools.reduce(lambda d, k: d[int(k) if isinstance(d, list) else k], keys_list, self)

    def set_by_path(self, keys_list, value):
        """Set item in config by path (list of keys)"""
        self.get_by_path(keys_list[:-1])[keys_list[-1]] = value

    def pop_by_path(self, keys_list):
        popped_value = self.get_by_path(keys_list[:-1]).pop(keys_list[-1])
        return popped_value

    def get_option(self, keyname):
        try:
            return self.get_by_path([keyname])
        except KeyError:
            return self.default

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

    def __delitem__(self, key):
        del self.config[key]

    def __iter__(self):
        return iter(self.config)

    def __len__(self):
        return len(self.config)

    @staticmethod
    def force_taint():
        """[DEPRECATED] toggle the changed state to True"""
        logger.warning(('[DEPRECATED] .force_taint is no more needed to mark '
                        'the config for a needed dump.'), stack_info=True)
