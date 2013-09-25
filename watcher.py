import time

from threading import Thread
from os import listdir
from os.path import join, dirname, normpath, exists

class Watcher(Thread):

    def __init__(self, target, callback, name='', recursive=False, interval=5):
        super(Watcher, self).__init__()
        self.target = target
        self.callback = callback

        self.interval = interval

        if exists(self.target):
            self.prevfiles = listdir(self.target)
        else:
            self.prevfiles = []

        self._checking = False

        self.killed = False

    def run(self):
        while not self.killed:
            try:
                time.sleep(self.interval)
                if not self._checking and exists(self.target):
                    self.check()
            except Exception as e:
                self.stop()

    def check(self):
        self._checking = True

        changed = self.changed_files()

        if changed:
            self.callback(changed)

        self._checking = False

    def changed_files(self):
        changed = []

        files = listdir(self.target)
        for item in files:
            r_path = join(self.target, item)

            if not item.startswith(('.', '_')) and item not in self.prevfiles:
                changed.append(r_path)

        self.prevfiles = files
        return changed

    def stop(self):
        self.killed = True



class ModuleWatcher():

    def __init__(self):
        self.watcher_by_dir = {}
        self.paths_by_dir = {}
        self.paths_by_interface = {}
        self.interfaces_by_path = {}

        self.on_module_change = None


    def add_paths(self, interface, paths):
        if interface not in self.paths_by_interface:
            self.paths_by_interface[interface] = set()

        for path in paths:
            dir_name = dirname(path)

            if dir_name not in self.paths_by_dir:
                self.paths_by_dir[dir_name] = []

            self.paths_by_dir[dir_name].append(path)
            self.paths_by_interface[interface].add(path)

            if path not in self.interfaces_by_path:
                self.interfaces_by_path[path] = []

            self.interfaces_by_path[path].append(interface)

            if dir_name not in self.watcher_by_dir:
                print('watcher created')
                watcher = Watcher(dir_name, self.change_listener, interval=2)
                watcher.start()
                self.watcher_by_dir[dir_name] = watcher


    def remove_paths(self, interface, paths):
        for path in paths:
            dir_name = dirname(path)
            dir_paths = self.paths_by_dir[dir_name]

            dir_paths.remove(path)
            self.paths_by_interface[interface].remove(path)
            self.interfaces_by_path[path].remove(interface)

            if not self.interfaces_by_path[path]:
                del self.interfaces_by_path[path]

            if not dir_paths:
                print('watcher stopped')
                watcher = self.watcher_by_dir[dir_name]
                watcher.stop()

                del self.watcher_by_dir[dir_name]
                del self.paths_by_dir[dir_name]

        if interface in self.paths_by_interface and not self.paths_by_interface[interface]:
            del self.paths_by_interface[interface]


    def set_errors(self, interface, errors):
        new_paths = set()
        for err in errors:
            file_name = err['text'][err['text'].index('\'')+2:-3]
            path = normpath(join(dirname(err['file']), file_name))

            new_paths.add(path)

        old_paths = self.paths_by_interface.get(interface, set())

        added_paths = new_paths - old_paths
        removed_paths = old_paths - new_paths

        self.add_paths(interface, added_paths)
        self.remove_paths(interface, removed_paths)

        if added_paths and self.on_module_change:
                self.on_module_change(interface)


    def clear_interface(self, interface):
        self.remove_paths(interface, self.paths_by_interface.get(interface, []).copy())


    def change_listener(self, changes):
        for path in changes:
            for interface in self.interfaces_by_path.get(path.split('.')[0], []):
                if self.on_module_change:
                    self.on_module_change(interface)


    def close_all(self):
        while self.watcher_by_dir:
            self.watcher_by_dir.popitem()[1].stop()
