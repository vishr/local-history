import sys
import os
import re
import time
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

def filtered_history_files(files):
    '''Only show file name in quick panel, not path'''
    if not settings.get('show_full_path', True):
        return [os.path.split(f)[1] for f in files]
    else:
        return files

def check_sbs_compare():
    prefs = sublime.load_settings("Preferences.sublime-settings")
    pcsets = sublime.load_settings("Package Control.sublime-settings")
    installed = "Compare Side-By-Side" in pcsets.get('installed_packages')
    ignored = "Compare Side-By-Side" in prefs.get('ignored_packages')
    if installed and not ignored:
        return True
    else:
        return False

def plugin_loaded():
    global settings

    settings = sublime.load_settings('LocalHistory.sublime-settings')
    settings.add_on_change('reload', sublime.load_settings('LocalHistory.sublime-settings'))

    status_msg('Target directory: "' + get_history_root() + '"')
    HistoryListener.listening = False

if sublime.version().startswith('2'):
    plugin_loaded()

def auto_diff_pane(view, index, history_dir, history_files):
    win = view.window()
    from_file = os.path.join(history_dir, history_files[index])
    from_file = from_file, os.path.basename(from_file)
    file_name = os.path.basename(view.file_name())
    to_file = view.file_name(), file_name
    group = win.get_view_index(view)[0]
    # view is not in first group
    if group:
        win.focus_group(0)
    # view is in first group
    elif win.num_groups() > 1:
        layout = win.get_layout()
        # only add to other group if pane is big enough
        if layout['cols'][2] - layout['cols'][1] > 0.35:
            win.focus_group(1)
        # create a pane in the middle
        else:
            middle_col = layout['cols'][1]
            layout['cols'].insert(1, middle_col)
            layout['cols'][1] = middle_col/2
            x1, y1, x2, y2 = layout['cells'][0]
            new_cell = [x1+1, y1, x2+1, y2]
            layout['cells'].insert(1, new_cell)
            new_cells = layout['cells'][:2]
            old_cells = [[x1+1, y1, x2+1, y2] for i, [x1, y1, x2, y2] in enumerate(layout['cells']) if i > 1]
            new_cells.extend(old_cells)
            layout['cells'] = new_cells
            win.run_command('set_layout', layout)
            for g, cell in enumerate(layout['cells']):
                if g > 0:
                    for view in win.views_in_group(g):
                        pos = win.get_view_index(view)[1]
                        win.set_view_index(view, g+1, pos)
            win.focus_group(1)
    else:
        win.run_command(
            "set_layout",
            {
                "cols": [0.0, 0.5, 1.0],
                "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
            }
        )
    view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file})
    # focus back to view
    win.focus_group(group)

def rename_tab(view, lh_view, pre, ext, snap=False):
    def delay():
        lh_file = os.path.basename(lh_view.file_name())
        name = pre+"-" if not snap else pre
        name = lh_file.replace(name, "")
        name = name.replace(ext, "")
        lh_view.set_syntax_file(view.settings().get("syntax"))
        lh_view.set_name(name)
    sublime.set_timeout_async(delay)

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
        skip_recently_saved = settings.get('skip_if_saved_within_minutes')

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
            elif skip_recently_saved:
                current_time = time.time()
                last_modified = os.path.getmtime(history_files[0])
                if current_time - last_modified < skip_recently_saved*60:
                    status_msg('File not saved, recent backup for "' + file_name + '" exists.')
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
            subprocess.call(['open', target_dir])
        elif system == 'Linux':
            subprocess.call('xdg-open %s' % target_dir, shell=True)
        elif system == 'Windows':
            subprocess.call('explorer %s' % target_dir, shell=True)

class HistoryOpen(sublime_plugin.TextCommand):

    def run(self, edit, autodiff=False):

        if not self.view.file_name():
            status_msg("not a valid file.")
            return

        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())
        pre, ext = os.path.splitext(file_name)

        history_files = get_history_files(file_name, history_dir)
        if not history_files:
            status_msg('Local History not found for "' + file_name + '".')
            return

        filtered_files = filtered_history_files(history_files)

        def on_done(index):
            if index is NO_SELECTION:
                return

            lh_view = self.view.window().open_file(os.path.join(history_dir, history_files[index]))
            sublime.set_timeout_async(lambda: lh_view.set_scratch(True))
            if settings.get('rename_tab'):
                rename_tab(self.view, lh_view, pre, ext)

            if settings.get('auto_diff') or autodiff:

                auto_diff_pane(self.view, index, history_dir, history_files)

        self.view.window().show_quick_panel(filtered_files, on_done)

class HistoryCompare(sublime_plugin.TextCommand):

    def run(self, edit, snapshots=False, sbs=False):

        if not self.view.file_name():
            status_msg("not a valid file.")
            return

        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())

        history_files = get_history_files(file_name, history_dir)
        history_files = history_files[1:]

        if history_files:
            filtered_files = filtered_history_files(history_files)
        else:
            status_msg('Local History not found for "' + file_name + '".')
            return

        def on_done(index):
            if index is NO_SELECTION:
                return

            if self.view.is_dirty() and settings.get('auto_save_before_diff', True):
                self.view.run_command('save')

            from_file = os.path.join(history_dir, history_files[index])
            from_file = from_file, os.path.basename(from_file)
            to_file = self.view.file_name(), file_name
            if sbs:
                HistorySbsCompare.vars = self.view, from_file[0], to_file[0]
                self.view.window().run_command("history_sbs_compare")
            else:
                self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file})

        self.view.window().show_quick_panel(filtered_files, on_done)

class HistoryReplace(sublime_plugin.TextCommand):

    def run(self, edit):

        if not self.view.file_name():
            status_msg("not a valid file.")
            return

        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())

        history_files = get_history_files(file_name, history_dir)
        history_files = history_files[1:]

        if history_files:
            filtered_files = filtered_history_files(history_files)
        else:
            status_msg('Local History not found for "' + file_name + '".')
            return

        def on_done(index):
            if index is NO_SELECTION:
                return

            # send vars to the listener for the diff/replace view
            from_file = os.path.join(history_dir, history_files[index])
            from_file = from_file, os.path.basename(from_file)
            to_file = self.view.file_name(), file_name
            HistoryReplaceDiff.from_file = from_file
            HistoryReplaceDiff.to_file = to_file
            HistoryListener.listening = True
            self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file, 'replace': True})

        self.view.window().show_quick_panel(filtered_files, on_done)

class HistoryIncrementalDiff(sublime_plugin.TextCommand):

    def run(self, edit):
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())

        history_files = get_history_files(file_name, history_dir)
        if len(history_files) < 2:
            status_msg('Incremental diff not found for "' + file_name + '".')
            return

        filtered_files = filtered_history_files(history_files)

        def on_done(index):
            if index is NO_SELECTION:
                return

            if index == len(history_files) - 1:
                status_msg('Incremental diff not found for "' + file_name + '".')
                return

            from_file = os.path.join(history_dir, history_files[index + 1])
            to_file = os.path.join(history_dir, history_files[index])
            self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file})

        self.view.window().show_quick_panel(filtered_files, on_done)

class ShowDiff(sublime_plugin.TextCommand):

    header = "\n-\n-    PRESS CTRL+ALT+ENTER TO ACCEPT AND REPLACE\n-\n\n"

    def run(self, edit, replace=False, **kwargs):
        from_file = kwargs['from_file'][0]
        to_file = kwargs['to_file'][0]
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
        panel.set_name("## LH: Diff ##")
        panel.set_scratch(True)
        panel.set_syntax_file('Packages/Diff/Diff.sublime-syntax')
        if replace and diff:
            HistoryListener.diff_view = panel
            panel.insert(edit, 0, self.header+diff)
        elif diff:
            panel.insert(edit, 0, diff)
        else:
            f1, f2 = os.path.split(from_file)[1], os.path.split(to_file)[1]
            panel.insert(edit, 0, "\n--- "+f1+"\n+++ "+f2+"\n\nNo differences\n\n\n")
        panel.set_read_only(True)

class HistoryDeleteAll(sublime_plugin.TextCommand):

    def run(self, edit):
        if not sublime.ok_cancel_dialog('Are you sure you want to delete the Local History for all files?'):
            return

        shutil.rmtree(get_history_root())
        status_msg('The Local History has been deleted for all files.')

class HistoryCreateSnapshot(sublime_plugin.TextCommand):

    def on_done(self, string):
        self.string = string
        self.view.window().run_command('history_create_snapshot', {"callback": True})

    def run(self, edit, callback=None):

        if not callback:
            v = self.view

            file_name = os.path.basename(v.file_name())
            self.pre, self.ext = os.path.splitext(file_name)
            c = "Enter a name for this snapshot:  "
            s = ""

            v.window().show_input_panel(c, s, self.on_done, None, None)

        else:
            v = self.view
            file_name = self.pre + " # " + self.string + self.ext
            history_dir = get_history_subdir(v.file_name())
            shutil.copyfile(v.file_name(), os.path.join(history_dir, file_name))
            status_msg('File snapshot saved under "' + file_name + '".')

class HistoryOpenSnapshot(sublime_plugin.TextCommand):

    def run(self, edit, open=True, compare=False, replace=False, sbs=False, delete=False, autodiff=False):

        # ---------------

        def Compare(index):
            if self.view.is_dirty():
                self.view.run_command('save')

            from_file = os.path.join(history_dir, history_files[index])
            from_file = from_file, os.path.basename(from_file)
            to_file = self.view.file_name(), os.path.basename(self.view.file_name())

            if sbs:
                HistorySbsCompare.vars = self.view, from_file[0], to_file[0]
                self.view.window().run_command("history_sbs_compare")

            elif replace:
                # send vars to the listener for the diff/replace view
                HistoryReplaceDiff.from_file = from_file
                HistoryReplaceDiff.to_file = to_file
                HistoryListener.listening = True
                self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file, 'replace': True})
            else:
                self.view.run_command('show_diff', {'from_file': from_file, 'to_file': to_file})

        # ---------------

        if not self.view.file_name():
            status_msg("not a valid file.")
            return

        file_name = os.path.basename(self.view.file_name())
        history_dir = get_history_subdir(self.view.file_name())
        pre, ext = os.path.splitext(file_name)

        history_files = get_history_files(file_name, history_dir)
        fpat = pre+r" # .+"
        history_files = [re.search(fpat, file).group(0) for file in history_files
                         if re.search(fpat, file)]
        if not history_files:
            status_msg('No snapshots found for "' + file_name + '".')
            return

        def rename(file):
            pre, ext = os.path.splitext(file_name)
            base, msg = file.split(" # ", 1)
            msg = msg.replace(ext, "")
            return [base+ext, msg]

        show_files = [rename(file) for file in history_files]

        def on_done(index):
            if index is NO_SELECTION:
                return

            if compare or sbs or replace:
                Compare(index)
            elif delete:
                os.remove(os.path.join(history_dir, history_files[index]))
                status_msg("The snapshot "+history_files[index]+" has been deleted.")
            else:
                lh_view = self.view.window().open_file(os.path.join(history_dir, history_files[index]))
                sublime.set_timeout_async(lambda: lh_view.set_scratch(True))
                if settings.get('rename_tab'):
                    rename_tab(self.view, lh_view, pre, ext, snap=True)
                if settings.get('auto_diff') or autodiff:
                    auto_diff_pane(self.view, index, history_dir, history_files)

        self.view.window().show_quick_panel(show_files, on_done)


class HistoryDelete(sublime_plugin.TextCommand):

    def interval(self, edit, m, mode):

        choice = (
            ["Older than one year", mode],
            ["Older than six months", mode],
            ["Older than one month", mode],
            ["Older than one week", mode]
        )

        def on_done(index):
            if index is NO_SELECTION:
                return
            if index == 0:
                self.run(edit, ask=False, dir=m, before_last="year")
            elif index == 1:
                self.run(edit, ask=False, dir=m, before_last="months6")
            elif index == 2:
                self.run(edit, ask=False, dir=m, before_last="month")
            elif index == 3:
                self.run(edit, ask=False, dir=m, before_last="week")

        self.view.window().show_quick_panel(choice, on_done)

    def run(self, edit, ask=True, before_last=None, dir=False):

        if ask:

            i1 = "For all files, snapshots excluded"
            i2 = "Current folder only, snapshots excluded"

            choice = (
                ["Time interval", i1],
                ["Time interval", i2],
                ["All", "All files for all folders, no exceptions"]
            )

            def on_done(index):
                if index is NO_SELECTION:
                    return

                if index == 0:
                    self.interval(edit, False, i1)
                elif index == 1:
                    self.interval(edit, True, i2)
                elif index == 2:
                    self.view.window().run_command('history_delete_all')

            self.view.window().show_quick_panel(choice, on_done)
            return

        # ---------------

        # today
        current = time.time()

        folder = get_history_subdir(self.view.file_name()) if dir else get_history_root()
        base_name = os.path.splitext(os.path.split(self.view.file_name())[1])[0]

        for root, dirs, files in os.walk(folder):
            for f in files:
                file = os.path.join(root, f)
                if not os.path.isfile(file):
                    continue

                # skip snapshots
                if re.match(base_name+" # ", f):
                    continue

                # file last modified
                last_mod = os.path.getmtime(file)

                if before_last == "year":
                    if current - last_mod > 31536000:
                        os.remove(file)

                elif before_last == "months6":
                    if current - last_mod > 15811200:
                        os.remove(file)

                elif before_last == "month":
                    if current - last_mod > 2635200:
                        os.remove(file)

                elif before_last == "week":
                    if current - last_mod > 604800:
                        os.remove(file)

        if before_last == "year":
            status_msg('deleted files older than one year.')

        elif before_last == "months6":
            status_msg('deleted files older than six months.')

        elif before_last == "month":
            status_msg('deleted files older than one month.')

        elif before_last == "week":
            status_msg('deleted files older than one week.')

class HistorySbsCompare(sublime_plugin.ApplicationCommand):

    def run(self, callback=False):
        global sbsW, sbsF, sbsVI

        if callback:
            view = sbsW.find_open_file(sbsF)
            sbsW.set_view_index(view, sbsVI[0], sbsVI[1])

        sbsV, sbsF1, sbsF2 = self.vars
        sbsW = sbsV.window()
        sbsVI = sbsW.get_view_index(sbsV)
        sbsW.run_command("sbs_compare_files", {"A": sbsF1, "B": sbsF2})

        # file has been closed, open it again
        sublime.set_timeout_async(lambda: sbsW.open_file(sbsF2), 1000)
        sublime.set_timeout_async(lambda: sbsW.run_command(
                "history_sbs_compare", {"callback": True}), 2000)

    def is_visible(self):
        return check_sbs_compare()

class HistoryMenu(sublime_plugin.TextCommand):

    def compare(self):

        choice = [
            ["Diff with history"],
            ["Diff wih snapshot"],
            ["Diff & Replace with history"],
            ["Diff & Replace wih snapshot"],
            ["Compare Side-By-Side with history"],
            ["Compare Side-By-Side wih snapshot"],
        ]

        def on_done(index):
            if index is NO_SELECTION:
                return
            if index == 0:
                self.view.window().run_command('history_compare')
            elif index == 1:
                self.view.window().run_command('history_open_snapshot', {"compare": True})
            if index == 2:
                self.view.window().run_command('history_replace')
            elif index == 3:
                self.view.window().run_command('history_open_snapshot', {"replace": True})
            elif index == 4:
                self.view.window().run_command('history_compare', {"sbs": True})
            elif index == 5:
                self.view.window().run_command('history_open_snapshot', {"sbs": True})
        sbs = check_sbs_compare()
        choice = choice if sbs else choice[:4]
        self.view.window().show_quick_panel(choice, on_done)

    def snapshots(self):

        choice = [
            ["Open"],
            ["Create"],
            ["Delete"],
            ["Compare"],
            ["Compare & Replace"],
            ["Compare Side-By-Side wih snapshot"],
        ]

        def on_done(index):
            if index is NO_SELECTION:
                return
            elif index == 0:
                self.view.window().run_command('history_open_snapshot')
            elif index == 1:
                self.view.window().run_command('history_create_snapshot')
            elif index == 2:
                self.view.window().run_command('history_open_snapshot', {"delete": True})
            elif index == 3:
                self.view.window().run_command('history_open_snapshot', {"compare": True})
            elif index == 4:
                self.view.window().run_command('history_open_snapshot', {"replace": True})
            elif index == 5 and sbs:
                self.view.window().run_command('history_open_snapshot', {"sbs": True})

        sbs = check_sbs_compare()
        choice = choice if sbs else choice[:5]
        self.view.window().show_quick_panel(choice, on_done)

    def run(self, edit, compare=False, snapshots=False):

        choice = (
            ["Open history"],
            ["Compare & Replace"],
            ["Snapshots"],
            ["Browse in Explorer"],
            ["Delete history"]
        )

        if compare:
            self.compare()
            return
        elif snapshots:
            self.snapshots()
            return

        def on_done(index):
            if index is NO_SELECTION:
                return
            elif index == 0:
                self.view.window().run_command('history_open')
            elif index == 1:
                self.view.window().run_command('history_menu', {"compare": True})
            elif index == 2:
                self.view.window().run_command('history_menu', {"snapshots": True})
            elif index == 3:
                self.view.window().run_command('history_browse')
            elif index == 4:
                self.view.window().run_command('history_delete')

        self.view.window().show_quick_panel(choice, on_done)

class HistoryReplaceDiff(sublime_plugin.TextCommand):
    from_file, to_file = None, None

    def run(self, edit):
        HistoryListener.listening = False
        from_file, to_file = HistoryReplaceDiff.from_file, HistoryReplaceDiff.to_file
        shutil.copyfile(from_file[0], to_file[0])
        status_msg('"'+to_file[1]+'"'+' replaced with "' + from_file[1] + '".')
        self.view.window().run_command('close_file')


class HistoryListener(sublime_plugin.EventListener):
    listening = False

    def on_query_context(self, view, key, operator, operand, match_all):

        if HistoryListener.listening:
            if key == "replace_diff":
                if view == HistoryListener.diff_view:
                    return True
            else:
                HistoryListener.listening = False
        return None

    def on_close(self, view):
        HistoryListener.listening = False
