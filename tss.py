import sublime
import threading
import subprocess
import json
import time
from os import path
from .util import get_cursor_rowcol

base_dir = path.dirname(path.abspath(__file__))
tss_file = path.join(base_dir, 'tss\\tss.js')


def to_tss_path(p):
	p = path.abspath(p).replace('\\', '/')
	return p[0].lower() + p[1:]


class TSSInterface():

	def __init__(self):
		self.files = None

		self._lock = threading.Lock()
		self._closed = False


	def _connect(self, root_file):
		si = subprocess.STARTUPINFO()
		si.dwFlags = subprocess.STARTF_USESHOWWINDOW

		self._process = subprocess.Popen(['node', tss_file, root_file], stdin=subprocess.PIPE, stdout=subprocess.PIPE, startupinfo=si)
		result = self._process.stdout.readline().decode('utf-8')

		if result != '"loaded {0}, TSS listening.."\n'.format(root_file):
			raise Exception('Invalid file ' + root_file)

		self.files = [f for f in self._run('files') if not f.startswith(to_tss_path(path.dirname(tss_file)))]


	def _close(self):
		with self._lock:
			self._process.kill()
			self._closed = True


	def _run(self, data):
		data += '\n'
		lock_timer = time.monotonic()

		with self._lock:
			if self._closed:
				return ""

			init_timer = time.monotonic()
			print('>', data[:-1][:60], '...')
			self._process.stdin.write(data.encode('utf-8'))
			result = self._process.stdout.readline().decode('utf-8')
			print('<', result[:-1][:60], '...')

		end_timer = time.monotonic()
		print('Took {0}ms in total({1}ms processing, {2}ms locked)'.format(
			  str(int((end_timer - lock_timer) * 1000)),
			  str(int((end_timer - init_timer) * 1000)),
			  str(int((init_timer - lock_timer) * 1000))));

		return json.loads(result)


	def reload(self):
		self._run('reload')
		self.files = [f for f in self._run('files') if not f.startswith(to_tss_path(path.dirname(tss_file)))]


	def get_errors(self):
		errors = self._run('showErrors')
		for error in errors:
			start = error['start']
			end = error['end']

			error['start'] = (start['line'] - 1, start['character'] - 1)
			error['end'] = (end['line'] - 1, end['character'] - 1)

			description_index = error['text'].index(':')
			space_index = error['text'].index(' ')

			error['code'] = error['text'][space_index + 1:description_index]
			error['text'] = error['text'][description_index + 2:]

			error['level'] = 'warning' if error['phase'] == 'Semantics' else 'illegal'

			del error['phase']
			del error['category']

		return errors


	def get_completions(self, view, rowcol=(None, None)):
		row, col = rowcol
		if not col:
			row, col = get_cursor_rowcol(view)

		file_name = to_tss_path(view.file_name())
		result = self._run('completions false {0} {1} {2}'.format(row + 1, col + 1, file_name))

		if result:
			return [{'name': c['name'], 'type': c['type']} for c in result['entries']]
		else:
			return []


	def update(self, view):
		content = view.substr(sublime.Region(0, view.size()))
		lines = len(content.split('\n'))
		file_name = to_tss_path(view.file_name())

		self._run('update {0} {1}\n{2}'.format(lines, file_name, content))


class InterfaceCollection():

	def __init__(self, interfaces):
		self.interfaces = interfaces.copy()


	def __getattr__(self, name):
		def virtualfunc(*args, **kargs):
			results = []
			for interface in self.interfaces:
				func = getattr(interface, name)
				results.append(tuple([interface, func(*args, **kargs)]))

			return results

		return virtualfunc


	def __getitem__(self, key):
		return self.interfaces[key]


	def __hash__(self):
		xor = 0
		for interface in self.interfaces:
			xor ^= hash(interface)

		return xor


class TSSFile():

	def __init__(self, path, interface):
		self.path = path
		self.interfaces = [interface]
		self.views = []


class InterfaceManager():

	def __init__(self):
		self.file_by_path = {}
		self.file_by_view = {}

		self.active_paths_by_interface = {}

		#Events triggered on some actions.
		self.on_view_added = None
		self.on_view_removed = None
		self.on_file_rename = None

		self._lock = threading.RLock()


	def add_interface(self, interface, paths):
		new_paths = set(paths)
		for path in new_paths:
			f = self.file_by_path.get(path)

			if f:
				f.interfaces.append(interface)

				for conflicting in f.interfaces:
					if conflicting == interface:
						continue

					conflicting_paths = self.active_paths_by_interface[conflicting]
					for conflicting_path in (new_paths & conflicting_paths):
						self.active_paths_by_interface[interface].add(conflicting_path)

					if new_paths.issuperset(conflicting_paths):
						self.close_interface(conflicting)

				for view in f.views:
					if self.on_view_added:
						self.on_view_added(view, InterfaceCollection([interface]))
			else:
				self.file_by_path[path] = TSSFile(path, interface)


	def remove_interface(self, interface, paths):
		for path in paths:
			f = self.file_by_path[path]
			f.interfaces.remove(interface)

			if not len(f.interfaces):
				views = f.views.copy()
				for view in views:
					self.remove(view)

				del self.file_by_path[path]

				for view in views:
					self.add(view)


	def create_interface(self, root_path):
		interface = TSSInterface()
		interface._connect(root_path)

		self.active_paths_by_interface[interface] = set()
		self.add_interface(interface, interface.files)


	def close_interface(self, interface):
		self.remove_interface(interface, interface.files)

		del self.active_paths_by_interface[interface]
		interface._close()


	def relative_interfaces(self, interface):
		relative_interfaces = set()
		for path in interface.files:
			f = self.file_by_path[path]
			relative_interfaces.update(set(f.interfaces))

		relative_interfaces.remove(interface)
		return relative_interfaces


	def add(self, view):
		if view.id() in self.file_by_view:
			raise Exception('Tried adding already handled view')

		with self._lock:
			path = to_tss_path(view.file_name())

			if path not in self.file_by_path:
				self.create_interface(path)

			f = self.file_by_path[path]
			f.views.append(view)
			self.file_by_view[view.id()] = f

			for interface in f.interfaces:
				self.active_paths_by_interface[interface].add(path)

		if self.on_view_added:
			self.on_view_added(view, InterfaceCollection(f.interfaces))

		return InterfaceCollection(f.interfaces)


	def remove(self, view):
		with self._lock:
			f = self.file_by_view[view.id()]
			del self.file_by_view[view.id()]

			f.views.remove(view)

			if not len(f.views):
				for interface in f.interfaces.copy():
					active_paths = self.active_paths_by_interface[interface]
					active_paths.remove(f.path)

					if not len(active_paths):
						self.close_interface(interface)

					else:
						relative_interfaces = self.relative_interfaces(interface)
						for relative in relative_interfaces:
							if self.active_paths_by_interface[relative].issuperset(active_paths):
								self.close_interface(interface)

		if self.on_view_removed:
			self.on_view_removed(view)


	def get(self, view):
		path = to_tss_path(view.file_name())
		f = self.file_by_view[view.id()]

		if path != f.path:
			old_interface = InterfaceCollection(f.interfaces)
			self.remove(view)

			if self.on_file_rename:
				self.on_file_rename(old_interface)

			return self.add(view)

		return InterfaceCollection(f.interfaces)


	def reload(self, interface_collection):
		for interface in interface_collection.interfaces:
			if interface._closed:
				continue

			old_paths = set(interface.files)
			interface.reload()
			new_paths = set(interface.files)

			added_paths = new_paths - old_paths
			removed_paths = old_paths - new_paths

			self.remove_interface(interface, removed_paths)
			self.add_interface(interface, added_paths)


	def close_all(self):
		all_views = []
		for f in self.file_by_path.values():
			for view in f.views:
				if view not in all_views:
					all_views.append(view)

		for view in all_views:
			self.remove(view)
