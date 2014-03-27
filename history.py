import sys
import os
import glob
import platform
import time
from datetime import datetime as dt
import difflib
import filecmp
import shutil
from threading import Thread
import subprocess
import sublime
import sublime_plugin

#==============#
#   Messages   #
#==============#
NO_HISTORY_MSG = 'No local history found'
NO_INCREMENTAL_DIFF = 'No incremental diff found'
HISTORY_DELETED_MSG = 'All local history deleted'

PY2 = sys.version_info < (3, 0)
S = sublime.load_settings('LocalHistory.sublime-settings')

# For ST3
def plugin_loaded():
    global S
    S = sublime.load_settings('LocalHistory.sublime-settings')

def get_history_path():
    default_history_path = os.path.join(os.path.abspath(os.path.expanduser('~')), '.sublime', 'history')
    return S.get("history_path", default_history_path)

def get_file_dir(file_path, history_path=None):
    if history_path is None:
        history_path = get_history_path()
    file_dir = os.path.dirname(file_path)
    if platform.system() == 'Windows':
        if file_dir.find(os.sep) == 0:
            file_dir = file_dir[2:]  # Strip the network \\ starting path
        if file_dir.find(':') == 1:
            file_dir = file_dir.replace(':', '', 1)
    else:
        file_dir = file_dir[1:]  # Trim the root
    return os.path.join(history_path, file_dir)


class HistorySave(sublime_plugin.EventListener):

    def on_close(self, view):
        if S.get('history_on_close'):
            t = Thread(target=self.process_history, args=(view.file_name(),))
            t.start()

    def on_post_save(self, view):
        if not S.get('history_on_close'):
            S.get('file_size_limit')
            t = Thread(target=self.process_history, args=(view.file_name(),
                get_history_path(),
                S.get('file_size_limit'),
                S.get('history_retention')))
            t.start()

    def process_history(self, file_path, history_path, file_size_limit, history_retention):
        if PY2:
            file_path = file_path.encode('utf-8')
        # Return if file exceeds the size limit
        if os.path.getsize(file_path) > file_size_limit:
            print ('WARNING: Local History did not save a copy of this file \
                because it has exceeded {0}KB limit.'.format(file_size_limit / 1024))
            return

        # Get history directory
        file_name = os.path.basename(file_path)
        history_dir = get_file_dir(file_path, history_path)
        if not os.path.exists(history_dir):
            # Create directory structure
            os.makedirs(history_dir)

        # Get history files
        os.chdir(history_dir)
        history_files = glob.glob('*' + file_name)
        history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

        # Skip if no changes
        if history_files:
            if filecmp.cmp(file_path, os.path.join(history_dir, history_files[0])):
                return

        # Store history
        shutil.copyfile(file_path, os.path.join(history_dir,
            '{0}.{1}'.format(dt.now().strftime('%Y-%m-%d_%H.%M.%S'),
                file_name)))

        # Remove old files
        now = time.time()
        for file in history_files:
            if os.path.getmtime(file) < now - history_retention * 86400: # convert to seconds
                os.remove(file)


class HistoryBrowse(sublime_plugin.TextCommand):

    def run(self, edit):
        system = platform.system()
        if system == 'Darwin':
            subprocess.call(['open', get_file_dir(self.view.file_name())])
        elif system == 'Linux':
            subprocess.call(['xdg-open', get_file_dir(self.view.file_name())])
        elif system == 'Windows':
            subprocess.call(['explorer', get_file_dir(self.view.file_name())])


class HistoryOpen(sublime_plugin.TextCommand):

    def run(self, edit):
        # Get history directory
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_file_dir(self.view.file_name())

        # Get history files
        try:
            os.chdir(history_dir)
        except OSError:
            sublime.status_message(NO_HISTORY_MSG)
            return
        history_files = glob.glob('*' + file_name)
        history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        if not history_files:
            sublime.status_message(NO_HISTORY_MSG)
            return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Open
            self.view.window().open_file(os.path.join(history_dir, history_files[index]))

        self.view.window().show_quick_panel(history_files, on_done)


class HistoryCompare(sublime_plugin.TextCommand):

    def run(self, edit):
        # Get history directory
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_file_dir(self.view.file_name())

        # Get history files
        os.chdir(history_dir)
        history_files = glob.glob('*' + file_name)
        history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        # Skip the first one as its always identical
        history_files = history_files[1:]

        if not history_files:
            sublime.status_message(NO_HISTORY_MSG)
            return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Trigger save before comparing, if required!
            if self.view.is_dirty():
                self.view.run_command('save')

            # Show diff
            from_file = os.path.join(history_dir, history_files[index])
            to_file = self.view.file_name()
            self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file})

        self.view.window().show_quick_panel(history_files, on_done)


class HistoryIncrementalDiff(sublime_plugin.TextCommand):

    def run(self, edit):
        # Get history directory
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_file_dir(self.view.file_name())

        # Get history files
        os.chdir(history_dir)
        history_files = glob.glob('*' + file_name)
        history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        if len(history_files) < 2:
            sublime.status_message(NO_INCREMENTAL_DIFF)
            return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Selected the last file
            if index == len(history_files) - 1:
                sublime.status_message(NO_INCREMENTAL_DIFF)
                return

            # Show diff
            from_file = os.path.join(history_dir, history_files[index + 1])
            to_file = os.path.join(history_dir, history_files[index])
            self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file})

        self.view.window().show_quick_panel(history_files, on_done)


class ShowDiff(sublime_plugin.TextCommand):

    def run(self, edit, **kwargs):
        from_file = kwargs['from_file']
        to_file = kwargs['to_file']
        # From
        if PY2:
            from_file = from_file.encode('utf-8')
            with open(from_file, 'r') as f:
                from_content = f.readlines()
        else:
            with open(from_file, 'r', encoding='utf-8') as f:
                from_content = f.readlines()

        # To
        if PY2:
            to_file = to_file.encode('utf-8')
            with open(to_file, 'r') as f:
                to_content = f.readlines()
        else:
            with open(to_file, 'r', encoding='utf-8') as f:
                to_content = f.readlines()

        # Compare and show diff
        diff = difflib.unified_diff(from_content, to_content, from_file, to_file)
        diff = ''.join(diff)
        if PY2:
            diff = diff.decode('utf-8')
        panel = sublime.active_window().new_file()
        panel.set_scratch(True)
        panel.set_syntax_file('Packages/Diff/Diff.tmLanguage')
        panel.insert(edit, 0, diff)


class HistoryDeleteAll(sublime_plugin.TextCommand):

    def run(self, edit):
        shutil.rmtree(get_history_path())
        sublime.status_message(HISTORY_DELETED_MSG)
