import sublime_plugin
import sublime

from functools import partial

from .tss import InterfaceManager, InterfaceCollection
from .errors import ErrorManager
from .watcher import ModuleWatcher
from . import util

interface_manager = InterfaceManager()
error_manager = ErrorManager(interface_manager)
module_watcher = ModuleWatcher()

def get_errors(view=None, tss=None):
    #Getting the interface before actually running the code,
    #so it won't do anything if the interface is closed before
    #really_get_errors is ran, this prevents us from getting
    #the errors two times if the interface is readded.
    if not tss:
        tss = interface_manager.get(view)

    def really_get_errors():
        results = tss.get_errors()
        for interface, errors in results:
            module_errors = [e for e in errors if e['code'] == 'TS2071']
            module_watcher.set_errors(interface, module_errors)

            error_manager.parse(errors, interface)

    #The views are updated separatelly from the errors so it is
    #guaranteed that every view of the project will be updated
    #before the error getter kicks in.
    if view:
        util.debounce(tss.update, 1, 'update' + str(view.id()), view)
    util.debounce(really_get_errors, 1.5, 'get_errors' + str(hash(tss)))


def update_status_message(view):
    errors = error_manager.get(view, view.sel()[0].a)
    msg = '; '.join([e['text'] for e in errors])

    if len(msg) > 200:
        msg = msg[:197] + '...'

    sublime.status_message(msg)


completions_by_view = {}
def update_completions(view):
    tss = interface_manager.get(view)[0]
    pos = util.get_cursor_rowcol(view)

    util.remove_debounce('update' + str(view.id()))
    tss.update(view)

    completions = tss.get_completions(view, pos)
    completions_by_view[view.id()] = completions

    if completions:
        view.run_command('auto_complete', {
            'disable_auto_insert': True,
            'next_completion_if_showing': True
        })

def get_completions(view):
    completions = completions_by_view.get(view.id())

    if completions is None:
        sublime.set_timeout_async(lambda: update_completions(view), 0)
        completions_by_view[view.id()] = 'Loading'
        completions = []

    elif type(completions) is list:
        completions = completions_by_view[view.id()]
        completions = [[c['name'] + '\t' + (c['type'] or ''), c['name']] for c in completions]

        del completions_by_view[view.id()]

    else:
        completions = []

    return (completions, sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)


def on_file_type_change(view):
    if util.is_typescript(view) and not interface_manager.get(view):
        interface_manager.add(view)

    elif not util.is_typescript(view) and interface_manager.get(view):
        interface_manager.remove(view)


def on_file_rename(old_tss, new_tss):
    interface_manager.reload(old_tss)
    get_errors(tss=old_tss)


def on_module_change(tss):
    tss = InterfaceCollection([tss])
    interface_manager.reload(tss)
    get_errors(tss=tss)


interface_manager.on_view_added = get_errors
interface_manager.on_view_removed = error_manager.clear_view

interface_manager.on_file_added = error_manager.add_file
interface_manager.on_file_removed = error_manager.remove_file

interface_manager.on_file_rename = on_file_rename

module_watcher.on_module_change = on_module_change


class SubtypeListener(sublime_plugin.EventListener):

    @util.typescript_view
    def on_load_async(self, view):
        interface_manager.add(view)

    def on_clone_async(self,view):
        self.on_load_async(view)


    @util.typescript_view
    def on_modified_async(self, view):
        get_errors(view)


    @util.typescript_view
    def on_post_save_async(self, view):
        get_errors(view)
        error_manager.list_errors()


    @util.typescript_view
    def on_close(self, view):
        interface_manager.remove(view)


    @util.typescript_view
    def on_selection_modified_async(self, view):
        update_status_message(view)


    @util.typescript_view
    def on_query_completions(self, view, prefix, locations):
        return get_completions(view)


    def on_text_command(self, view, cmd, args):
        if cmd == 'set_file_type':
            sublime.set_timeout_async(lambda: on_file_type_change(view), 0)



def plugin_loaded():
    for window in sublime.windows():
        for view in window.views():
            if util.is_typescript(view):
                sublime.set_timeout_async(partial(interface_manager.add, view), 0)


def plugin_unloaded():
    interface_manager.close_all()
    module_watcher.close_all()
