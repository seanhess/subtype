from os import path
import sublime
import sublime_plugin

base_dir = path.dirname(path.abspath(__file__))
icons_dir = path.join('..', path.basename(base_dir), 'icons')
illegal_icon = path.join(icons_dir, 'simple-illegal')
warning_icon = path.join(icons_dir, 'simple-warning')
draw_style = sublime.DRAW_STIPPLED_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE

class ErrorManager():

    def __init__(self, interface_manager):
        self.interface_manager = interface_manager
        self.errors_by_path = {}
        self.errors_by_viewid = {}


    def add_file(self, f):
        self.errors_by_path[f.path] = []


    def remove_file(self, f):
        del self.errors_by_path[f.path]


    def draw_errors(self, view, errors):
        illegals = []
        warnings = []

        for e in errors:
            if not e.get('region'):
                start = view.text_point(*e['start'])
                end = view.text_point(*e['end'])
                e['region'] = sublime.Region(start, end)

            if e['level'] == 'illegal':
                illegals.append(e['region'])
            else:
                warnings.append(e['region'])

        view.add_regions('typescript-illegal', illegals, 'sublimelinter.outline.illegal', illegal_icon, draw_style)
        view.add_regions('typescript-warning', warnings, 'sublimelinter.outline.warning', warning_icon, draw_style)

        self.errors_by_viewid[view.id()] = errors


    def parse(self, errors, interface):
        all_views = []

        self.clear_interface(interface)

        errors_by_path = {}

        for e in errors:
            if e['file'] not in errors_by_path:
                errors_by_path[e['file']] = []

            errors_by_path[e['file']].append(e)

        for path in errors_by_path.keys():
            for view in self.interface_manager.get_views(path):
                self.draw_errors(view, errors_by_path[path])

        self.errors_by_path.update(errors_by_path)


    def clear_interface(self, interface):
        if self.interface_manager.get_active_paths(interface):
            for path in interface.files:
                for view in self.interface_manager.get_views(path):
                    self.clear_view(view)

                if path not in self.errors_by_path:
                    raise Exception('Handling errors for unkown file')

                self.errors_by_path[path] = []

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


    def output_create(self):
        self.output = sublime.active_window().create_output_panel('typescript_errors')
        self.output.set_syntax_file("Packages/subtype/theme/TypescriptBuild.tmLanguage")
        self.output.settings().set("color_scheme", "Packages/subtype/theme/TypescriptBuild.tmTheme")


    def output_open(self):
        sublime.active_window().run_command("show_panel", {"panel": "output.typescript_errors"})


    def output_close(self):
        sublime.active_window().run_command("hide_panel", {"panel": "output.typescript_errors"})


    def output_append(self, characters):
        self.output.run_command('append', {'characters': characters})


    def list_errors(self):
        self.output_create()
        self.output.set_read_only(False)

        regions = []
        for path, errors in self.errors_by_path.items():
            if not errors:
                continue

            self.output_append('{0}\n'.format(path))

            for error in errors:
                region_text = 'Line {0}:'.format(error['start'][0] + 1)
                region_start = self.output.size() + 2
                regions.append(sublime.Region(region_start, region_start + len(region_text)))
                self.output_append('  {0} {1}\n'.format(region_text, error['text']))

            self.output_append('\n')

        self.output.add_regions('typescript-illegal', regions, 'error.line', '', sublime.DRAW_NO_FILL)
        self.output.set_read_only(True)
        self.output_open()



class SubtypeErrorsListener(sublime_plugin.EventListener):

    def on_selection_modified_async(self, view):
        if view.settings().get('syntax').lower().endswith('typescriptbuild.tmlanguage'):
            error_regions = []
            error_regions.extend(view.get_regions('typescript-illegal'))
            error_regions.extend(view.get_regions('typescript-warning'))

            sel_point = view.sel()[0].a
            paths = view.substr(sublime.Region(0, view.size())).split('\n')

            last_file = None
            for x in range(len(paths)):
                if paths[x].startswith('  '):
                    paths[x] = last_file
                else:
                    last_file = paths[x]

            for region in error_regions:
                if region.contains(sel_point):
                    row = view.rowcol(sel_point)[0]
                    line = view.substr(region)[5:]
                    path = '{0}:{1}'.format(paths[row], line)
                    sublime.active_window().open_file(path, sublime.ENCODED_POSITION)
