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
		self.files = [f for f in self._run('files') if not f.startswith(path.dirname(tss_file))]


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



class InterfaceManager():

	def __init__(self):
		#Used to keep track of active interfaces.
		self.interfaces = {} #{Path : Interface}
		self.files = {} #{Interface : Active Paths}
		self.views = {} #{Path : Open Views}

		#Used to keep track of original view filenames.
		self.view_filenames = {}

		#Events triggered on some actions.
		self.on_view_added = None

		self._lock = threading.RLock()


	def get(self, view): #get_interface
		path = to_tss_path(view.file_name())

		#If a file is renamed remove and add it again so the
		#manager reflects it's new path, perhaps should create
		#a rename event, so the consumer can reload an interface
		#if there is a file rename.
		if view.id() in self.view_filenames and path != self.view_filenames[view.id()]: #Handle file renaming
			self.remove(view)
			self.add(view)
			return self.get(view)

		if path in self.interfaces:
			return self.interfaces[path]


	def create_interface(self, view):
		path = to_tss_path(view.file_name())

		interface = TSSInterface()
		interface._connect(path)

		#Save in temporary variables so it will not currupt
		#the state if the loop stops in the middle.
		new_interfaces = {}
		new_views = {}

		for f in interface.files:
			conflicting_interface = self.interfaces.get(f)
			if conflicting_interface:
				interface._close()

				files = set(interface.files)
				conflicting_files = set(conflicting_interface.files)

				if files.issuperset(conflicting_files):
					return self.reload(conflicting_interface, view)
				else:
					#Should probably handle this in a way that
					#two instances can share a single view.
					raise Exception('File conflict between two instances: ' + f)

			new_interfaces[f] = interface
			new_views[f] = []

		self.interfaces.update(new_interfaces)
		self.views.update(new_views)

		self.files[interface] = set()

		return interface


	def add(self, view): #add_view
		if view.id() in self.view_filenames:
			raise Exception('Tried to add already handled view')

		with self._lock:
			path = to_tss_path(view.file_name())
			self.view_filenames[view.id()] = path

			if path in self.interfaces:
				interface = self.interfaces[path]
			else:
				interface = self.create_interface(view)

			#Keep track of active interface files so we can close the
			#interface when there are no more active files
			self.files[interface].add(path)
			self.views[path].append(view)

		if self.on_view_added:
			self.on_view_added(view, interface)

		return interface


	def remove(self, view): #remove_view
		with self._lock:
			#The file path may have changed since it was added, so
			#we need to remove the references to it's original path.
			path = self.view_filenames[view.id()]
			interface = self.interfaces[path]

			self.views[path].remove(view)
			del self.view_filenames[view.id()]

			#If there are no more views poiting to a certain file,
			#the file is no longer active, if there are no active
			#files in an interface, that interface is not being used
			#and can be closed.
			if not len(self.views[path]):
				self.files[interface].remove(path)

				if not len(self.files[interface]):
					del self.files[interface]

					for f in interface.files:
						del self.interfaces[f]
						del self.views[f]

					interface._close()


	#This method has two use cases, to reload an interface and update
	#the manager state, and to rebase an interface around a view that
	#contains it's new root, it probably should be split when I implement
	#a reload based on TSS's reload.
	def reload(self, interface, root=None):
		views = []

		for f in self.files[interface]:
			views += self.views[f]

		for view in views:
			self.remove(view)

		new_interface = None
		if root:
			new_interface = self.create_interface(root)

		for view in views:
			self.add(view)

		return new_interface
