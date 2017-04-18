"""cache for a json file with shortscuts to access data"""

import asyncio
import collections
from datetime import datetime
import functools
import json
import glob
import logging
import operator
import os
import shutil
import time

logger = logging.getLogger(__name__)


class Config(collections.MutableMapping):
    """Configuration JSON storage class

    Args:
        path: string, file path of the config file
        default: any type, default value for missing data
        failsafe_backups: int, ammount of backups that should be kept
        save_delay: int, time in second a dump should be delayed
    """
    def __init__(self, path, default=None, failsafe_backups=0, save_delay=0):
        self.filename = path
        self.default = default
        self.config = {}
        self.defaults = {}
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
        """remove old backup files above the limit and create a new backup

        the limit refers to the number of .failsafe_backups

        Returns:
            boolean, True on a successful new backup, otherwise False
        """
        try:
            with open(self.filename) as file:
                json.load(file)
        except IOError:
            return False
        except ValueError:
            logger.warning("%s is corrupted, aborting backup", self.filename)
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
        """restore data from a recent backup

        Returns:
            boolean, True if any backup could be loaded, False if None is
                available or all backups are currupt or no readable
        """
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
                logger.error("corrupted recovery: %s", self.filename)
        return False

    def load(self):
        """Load config from file

        Raises:
            IOError: the existing config is not readable or no new config can
                be saved to the configured path
            ValueError: the config file is not a valid json and no backups are
                available
        """
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
        """force an immediate dump to file"""
        logger.info("flushing %s", self.filename)
        self.save(delay=False)

    def get_by_path(self, keys_list, fallback=True):
        """Get an item from .config by path

        Args:
            keys_list: list, a list of strings, describing the path to the value
            fallback: boolean, use the default values as fallback for missing
                entrys

        Returns:
            any type, the requested value

        Raises:
            KeyError, ValueError: the path does not exist
        """
        try:
            return self._get_by_path(self.config, keys_list)
        except (KeyError, ValueError):
            if not fallback:
                raise
            try:
                return self._get_by_path(self.defaults, keys_list)
            except (KeyError, ValueError):
                raise KeyError('%s has no path %s and there is no default set' %
                               (self.filename, keys_list))

    def set_by_path(self, keys_list, value, create_path=True):
        """set an item in .config by path

        Args:
            keys_list: list, a list of strings, describing the path to the value
            value: any type, the new value
            create_path: boolean, toogle to ensure an existing path

        Raises:
            KeyError, ValueError: the path does not exist
        """
        if create_path:
            self.ensure_path(keys_list)
        self.get_by_path(keys_list[:-1],
                         fallback=False)[keys_list[-1]] = value

    def pop_by_path(self, keys_list):
        """remove an item in .config found with the given path

        Args:
            keys_list: list, a list of strings, describing the path to the value

        Returns:
            any type, the removed value

        Raises:
            KeyError, ValueError: the path does not exist
        """
        return self.get_by_path(keys_list[:-1], False).pop(keys_list[-1])

    @staticmethod
    def _get_by_path(source, path):
        """Get an item from source by path

        Args:
            path: list, a list of strings, describing the path to the value

        Returns:
            any type, the requested value

        Raises:
            KeyError, ValueError: the path does not exist
        """
        if not len(path):
            return source
        return functools.reduce(operator.getitem, path[:-1], source)[path[-1]]

    def get_option(self, keyname):
        """get a top level entry from config or a default value

        Args:
            keyname: string, top level key

        Returns:
            any type, the requested value or .default if the key does not exist
        """
        try:
            return self.get_by_path([keyname])
        except KeyError:
            return self.default

    def get_suboption(self, grouping, groupname, keyname):
        """get a third level entry from config with a fallback to top level

        Args:
            grouping: string, top level entry in .config
            groupname: string, second level entry, key in grouping
            keyname: string, third level key as target and also the top level
                key as fallback for a missing key in the path

        Returns:
            any type, the requested value, it's fallback on top level or
                .default if the key does not exist on both level
        """
        try:
            return self.get_by_path([grouping, groupname, keyname])
        except KeyError:
            return self.get_option(keyname)

    def exists(self, keys_list, fallback=False):
        """check if a path exisits in the dict

        Args:
            keys_list: list, a list of strings describing the path
            fallback: boolean, use the default values as fallback for missing
                entrys

        Returns:
            boolean, True if the full path is resolvable, otherwise False
        """
        try:
            self.get_by_path(keys_list, fallback)
            return True
        except (KeyError, TypeError):
            return False

    def ensure_path(self, path, base=None):
        """create a path of dicts if the given path does not exist

        Args:
            path: list, a list of strings describing the path
            base: dict, the source to create the path in

        Returns:
            boolean, True if the path did not existed before, otherwise False

        Raises:
            AttributeError: on attempting to override a key pointing to an entry
                in config that is not a dict
        """
        if base is None:
            base = self.config
        created = not self.exists(path)
        last_key = None
        for level in path:
            try:
                base = base.setdefault(level, {})
                last_key = level
            except AttributeError:
                raise AttributeError('%s has no dict at "%s" in the path %s' %
                                     (self.filename, last_key, path))
        return created

    def set_defaults(self, source, path=None):
        """ensure that the dict, path points to, has the structure of the source

        also override to defaults if the type of an entry does not match

        Args:
            source: dict structure with values
            path: list, a list of keys to the dict to update with defaults

        Raises:
            ValueError: the path could not be created as it would override an
                entry that is not a dict
            AttributeError: a value in source does not match with the type that
                is already in the defaults
        """
        if path is None:
            path = []
        else:
            self.ensure_path(path, base=self.defaults)
        defaults = self._get_by_path(self.defaults, path)
        for key, value in source.items():
            if key not in defaults:
                defaults[key] = value

            elif isinstance(value, dict):
                self.set_defaults(value, path + [key])

            elif isinstance(value, list):
                defaults[key].extend(value)

    def validate(self, source, path=None):
        """ensure that the entrys in source are all available in the config

        Args:
            source: default dict structure with values
            path: list of keys to the dict to validate

        Raises:
            ValueError: the path could not be created as it would override an
                entry that is not a dict
        """
        if path is None:
            path = []
        for key, value in source.items():
            if not self.exists(path + [key]):
                self.set_by_path(path + [key], value)

            elif not isinstance(self.get_by_path(path + [key]), type(value)):
                self.set_by_path(path + [key], value)

            elif isinstance(value, dict) and len(value):
                self.validate(value, path + [key])

    def __getitem__(self, key):
        return self.get_option(key)

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
