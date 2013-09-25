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

        errors_by_path = {}

        for e in errors:
            views = self.interface_manager.file_by_path[e['file']].views
            if not len(views):
                continue

            view = views[0]

            start = view.text_point(*e['start'])
            end = view.text_point(*e['end'])
            e['region'] = sublime.Region(start, end)

            if e['file'] not in errors_by_path:
                errors_by_path[e['file']] = []

            errors_by_path[e['file']].append(e)

        for path in self.interface_manager.active_paths_by_interface.get(interface, []):
            path_errors = errors_by_path.get(path, [])
            illegals = [e['region'] for e in path_errors if e['level'] == 'illegal']
            warnings = [e['region'] for e in path_errors if e['level'] == 'warning']

            for view in self.interface_manager.file_by_path[path].views:
                self.errors_by_viewid[view.id()] = path_errors

                draw_style = sublime.DRAW_STIPPLED_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE

                view.add_regions('typescript-illegal', illegals, 'sublimelinter.outline.illegal', illegal_icon, draw_style)
                view.add_regions('typescript-warning', warnings, 'sublimelinter.outline.warning', warning_icon, draw_style)


    def clear_interface(self, interface):
        for path in self.interface_manager.active_paths_by_interface.get(interface, []):
            for view in self.interface_manager.file_by_path[path].views:
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
