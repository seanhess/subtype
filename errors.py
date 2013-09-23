from os import path
import sublime

base_dir = path.dirname(path.abspath(__file__))
icons_dir = path.join('..', path.basename(base_dir), 'icons')
illegal_icon = path.join(icons_dir, 'simple-illegal')
warning_icon = path.join(icons_dir, 'simple-warning')

class ErrorManager():

	def __init__(self, interface_manager):
		self.interface_manager = interface_manager
		self.errors_by_viewid = {}


	def parse(self, errors, interface):
		all_views = []

		self.clear_interface(interface)

		for e in errors:
			views = self.interface_manager.views[e['file']]

			if not len(views):
				continue

			view = views[0]

			start = view.text_point(*e['start'])
			end = view.text_point(*e['end'])
			e['region'] = sublime.Region(start, end)

			for view in views:
				if view not in all_views:
					all_views.append(view)

		for view in all_views:
			view_errors = [e for e in errors if path.samefile(e['file'], view.file_name())]
			self.errors_by_viewid[view.id()] = view_errors

			illegals = [e['region'] for e in view_errors if e['level'] == 'illegal']
			warnings = [e['region'] for e in view_errors if e['level'] == 'warning']

			draw_style = sublime.DRAW_STIPPLED_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE

			view.add_regions('typescript-illegal', illegals, 'sublimelinter.outline.illegal', illegal_icon, draw_style)
			view.add_regions('typescript-warning', warnings, 'sublimelinter.outline.warning', warning_icon, draw_style)


	def clear_interface(self, interface):
		#There is the possibility of the interface already being
		#closed before this is ran, so the manager has no views
		#associated with it, in that case we do nothing.
		for f in self.interface_manager.files.get(interface, []):
			for view in self.interface_manager.views[f]:
				self.clear_view(view)


	def clear_view(self, view):
		view.erase_regions('typescript-illegal')
		view.erase_regions('typescript-warning')

		if view.id() in self.errors_by_viewid:
			del self.errors_by_viewid[view.id()]


	def get(self, view, point=None):
		errors = self.errors_by_viewid.get(view.id(), [])

		if point is None:
			return errors
		else:
			return [e for e in errors if e['region'].contains(point)]
