from os import path
import threading

def get_cursor_rowcol(view):
	return view.rowcol(view.sel()[0].a)

def is_typescript(view):
	return view.file_name() and view.settings().get('syntax') == 'Packages/TypeScript/TypeScript.tmLanguage'

def typescript_view(f):
	def call_f(self, view, *args, **kargs):
		if is_typescript(view):
			return f(self, view, *args, **kargs)

	return call_f


debounced_timers = {}
def debounce(fn, delay, tag=None, *args):
	tag = tag if tag else fn

	if tag in debounced_timers:
		debounced_timers[tag].cancel()

	timer = threading.Timer(delay, fn, args)
	timer.start()

	debounced_timers[tag] = timer


def remove_debounce(tag):
	if tag in debounced_timers:
		debounced_timers[tag].cancel()
