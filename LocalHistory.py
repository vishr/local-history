import sys
import os
import platform
import datetime
import difflib
import filecmp
import shutil
from threading import Thread
import subprocess
import sublime
import sublime_plugin

PY2 = sys.version_info < (3, 0)

if PY2:
    from math import log
else:
    from math import log2

NO_SELECTION = -1
settings = None

def status_msg(msg):
    sublime.status_message('Local History: ' + msg)

def readable_file_size(size):
    suffixes = ['bytes', 'KB', 'MB', 'GB', 'TB', 'EB', 'ZB']
    if PY2:
        order = int(log(size, 2) / 10) if size else 0
    else:
        order = int(log2(size) / 10) if size else 0
    return '{:.4g} {}'.format(size / (1 << (order * 10)), suffixes[order])

def get_history_root():
    path_default_not_portable = os.path.join(os.path.abspath(os.path.expanduser('~')), '.sublime', 'Local History')
    path_not_portable = settings.get('history_path', path_default_not_portable)
    return os.path.join(os.path.dirname(sublime.packages_path()), '.sublime', 'Local History') if settings.get('portable', True) else path_not_portable

def get_history_subdir(file_path):
    history_root = get_history_root()

    file_dir = os.path.dirname(file_path)
    if platform.system() == 'Windows':
        if file_dir.find(os.sep) == 0:
            file_dir = file_dir[2:]
        if file_dir.find(':') == 1:
            file_dir = file_dir.replace(':', '', 1)
    else:
        file_dir = file_dir[1:]

    return os.path.join(history_root, file_dir)

def get_history_files(file_name, history_dir):
    file_root, file_extension = os.path.splitext(file_name)
    history_files = [os.path.join(dirpath, f)
                        for dirpath, dirnames, files in os.walk(history_dir)
                        for f in files if f.startswith(file_root) and f.endswith(file_extension)]
    history_files.sort(key=lambda f: os.path.getmtime(os.path.join(history_dir, f)), reverse=True)

    return history_files

def plugin_loaded():
    global settings

    settings = sublime.load_settings('LocalHistory.sublime-settings')
    settings.add_on_change('reload', sublime.load_settings('LocalHistory.sublime-settings'))

    status_msg('Target directory: "' + get_history_root() + '"')

if sublime.version().startswith('2'):
    plugin_loaded()


class HistorySave(sublime_plugin.EventListener):

    def on_load(self, view):
        if not PY2 or not settings.get('history_on_load', True):
            return

        t = Thread(target=self.process_history, args=(view.file_name(),))
        t.start()

    def on_load_async(self, view):
        if settings.get('history_on_load', True):
            t = Thread(target=self.process_history, args=(view.file_name(),))
            t.start()

    def on_close(self, view):
        if settings.get('history_on_close', True):
            t = Thread(target=self.process_history, args=(view.file_name(),))
            t.start()

    def on_post_save(self, view):
        if not PY2 or settings.get('history_on_close', True):
            return

        t = Thread(target=self.process_history, args=(view.file_name(),))
        t.start()

    def on_post_save_async(self, view):
        if not settings.get('history_on_close', True):
            t = Thread(target=self.process_history, args=(view.file_name(),))
            t.start()

    def on_deactivated(self, view):
        if (view.is_dirty() and settings.get('history_on_focus_lost', False)):
            t = Thread(target=self.process_history, args=(view.file_name(),))
            t.start()

    def process_history(self, file_path):
        if file_path == None:
            status_msg('File not saved, path does not exist.')
            return

        if not os.path.isfile(file_path):
            status_msg('File not saved, might be part of a package.')
            return

        size_limit = settings.get('file_size_limit', 4194304)
        history_retention = settings.get('history_retention', 0)

        if PY2:
            file_path = file_path.encode('utf-8')
        if os.path.getsize(file_path) > size_limit:
            status_msg('File not saved, exceeded %s limit.' % readable_file_size(size_limit))
            return

        file_name = os.path.basename(file_path)
        history_dir = get_history_subdir(file_path)
        if not os.path.exists(history_dir):
            os.makedirs(history_dir)

        history_files = get_history_files(file_name, history_dir)

        if history_files:
            if filecmp.cmp(file_path, os.path.join(history_dir, history_files[0])):
                status_msg('File not saved, no changes for "' + file_name + '".')
                return

        file_root, file_extension = os.path.splitext(file_name)
        shutil.copyfile(file_path, os.path.join(history_dir, '{0}-{1}{2}'.format(file_root, datetime.datetime.now().strftime(settings.get('format_timestamp', '%Y%m%d%H%M%S')), file_extension)))

        status_msg('File saved, updated Local History for "' + file_name + '".')

        if history_retention == 0:
            return

        max_valid_archive_date = datetime.date.today() - datetime.timedelta(days=history_retention)
        for file in history_files:
            file = os.path.join(history_dir, file)
            if datetime.date.fromtimestamp(os.path.getmtime(file)) < max_valid_archive_date:
                os.remove(file)

class HistorySaveNow(sublime_plugin.TextCommand):

    def run(self, edit):
        t = Thread(target=HistorySave().process_history, args=(self.view.file_name(),))
        t.start()

class HistoryBrowse(sublime_plugin.TextCommand):

    def run(self, edit):
        target_dir = get_history_subdir(self.view.file_name())
        target_dir = target_dir.replace('\\', os.sep).replace('/', os.sep)
        system = platform.system()

        if system == 'Darwin':
            subprocess.call('open %s' % target_dir)
        elif system == 'Linux':
            subprocess.call('xdg-open %s' % target_dir, shell=True)
        elif system == 'Windows':
            subprocess.call('explorer %s' % target_dir, shell=True)

class HistoryOpen(sublime_plugin.TextCommand):

    def run(self, edit):
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())

        history_files = get_history_files(file_name, history_dir)
        if not history_files:
            status_msg('Local History not found for "' + file_name + '".')
            return

        def on_done(index):
            if index is NO_SELECTION:
                return

            self.view.window().open_file(os.path.join(history_dir, history_files[index]))

        self.view.window().show_quick_panel(history_files, on_done)

class HistoryCompare(sublime_plugin.TextCommand):

    def run(self, edit):
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())

        history_files = get_history_files(file_name, history_dir)
        history_files = history_files[1:]

        if not history_files:
            status_msg('Local History not found for "' + file_name + '".')
            return

        def on_done(index):
            if index is NO_SELECTION:
                return

            if self.view.is_dirty():
                self.view.run_command('save')

            from_file = os.path.join(history_dir, history_files[index])
            to_file = self.view.file_name()
            self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file})

        self.view.window().show_quick_panel(history_files, on_done)

class HistoryReplace(sublime_plugin.TextCommand):

    def run(self, edit):
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())

        history_files = get_history_files(file_name, history_dir)
        history_files = history_files[1:]

        if not history_files:
            status_msg('Local History not found for "' + file_name + '".')
            return

        def on_done(index):
            if index is NO_SELECTION:
                return

            file = os.path.join(history_dir, history_files[index])
            with open(file) as f:
                data = f.read()
                if PY2:
                    data.decode('utf-8')
                self.view.replace(edit, sublime.Region(0, self.view.size()), data)
            self.view.run_command('save')

        self.view.window().show_quick_panel(history_files, on_done)

class HistoryIncrementalDiff(sublime_plugin.TextCommand):

    def run(self, edit):
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())

        history_files = get_history_files(file_name, history_dir)
        if len(history_files) < 2:
            status_msg('Incremental diff not found for "' + file_name + '".')
            return

        def on_done(index):
            if index is NO_SELECTION:
                return

            if index == len(history_files) - 1:
                status_msg('Incremental diff not found for "' + file_name + '".')
                return

            from_file = os.path.join(history_dir, history_files[index + 1])
            to_file = os.path.join(history_dir, history_files[index])
            self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file})

        self.view.window().show_quick_panel(history_files, on_done)

class ShowDiff(sublime_plugin.TextCommand):

    def run(self, edit, **kwargs):
        from_file = kwargs['from_file']
        to_file = kwargs['to_file']
        if PY2:
            from_file = from_file.encode('utf-8')
            with open(from_file, 'r') as f:
                from_content = f.readlines()
        else:
            with open(from_file, 'r', encoding='utf-8') as f:
                from_content = f.readlines()

        if PY2:
            to_file = to_file.encode('utf-8')
            with open(to_file, 'r') as f:
                to_content = f.readlines()
        else:
            with open(to_file, 'r', encoding='utf-8') as f:
                to_content = f.readlines()

        diff = difflib.unified_diff(from_content, to_content, from_file, to_file)
        diff = ''.join(diff)
        if PY2:
            diff = diff.decode('utf-8')
        panel = sublime.active_window().new_file()
        panel.set_scratch(True)
        panel.set_syntax_file('Packages/Diff/Diff.sublime-syntax')
        panel.insert(edit, 0, diff)

class HistoryDeleteAll(sublime_plugin.TextCommand):

    def run(self, edit):
        if not sublime.ok_cancel_dialog('Are you sure you want to delete the Local History for all files?'):
            return

        shutil.rmtree(get_history_root())
        status_msg('The Local History has been deleted for all files.')
