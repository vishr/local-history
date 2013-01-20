import sublime
import sublime_plugin
import os
import glob
import platform
from datetime import datetime as dt
import difflib
import filecmp
import shutil
from threading import Thread

#==============#
#   Settings   #
#==============#
settings = sublime.load_settings("LocalHistory.sublime-settings")
history_location = settings.get("history_location", "~")
if history_location == "~":
    history_location = os.path.expanduser("~")
HISTORY_PATH = os.path.join(os.path.abspath(history_location), ".sublime", "history")
HISTORY_LIMIT = settings.get("history_limit", 50)
FILE_SIZE_LIMIT = settings.get("file_size_limit", 262144)


def show_diff(window, from_file, to_file):
    # From
    from_file = from_file.encode("utf-8")
    with open(from_file, "r") as f:
        from_content = f.readlines()

    # To
    to_file = to_file.encode("utf-8")
    with open(to_file, "r") as f:
        to_content = f.readlines()

    # Compare and show diff
    diff = difflib.unified_diff(from_content, to_content, from_file, to_file)
    diff = "".join(diff).decode("utf-8")
    panel = window.new_file()
    panel.set_scratch(True)
    panel.set_syntax_file("Packages/Diff/Diff.tmLanguage")
    panel_edit = panel.begin_edit()
    panel.insert(panel_edit, 0, diff)
    panel.end_edit(panel_edit)


def get_filedir(file_path):
    file_dir = os.path.dirname(file_path)
    if platform.system() == "Windows":
        if file_dir.find("\\") == 0:
            file_dir = file_dir[2:]  # Strip the network \\ starting path
        if file_dir.find(":") == 1:
            file_dir = file_dir.replace(":", "", 1)
    else:
        file_dir = file_dir[file_dir.find(os.sep) + 1:]  # Trim the root
    return os.path.join(HISTORY_PATH, file_dir)


class HistorySave(sublime_plugin.EventListener):

    def on_post_save(self, view):

        def run(file_path):
            file_path = file_path.encode("utf-8")
            # Return if file exceeds the size limit
            if os.path.getsize(file_path) > FILE_SIZE_LIMIT:
                print "WARNING: Local History did not save a copy of this file \
                    because it has exceeded {0}KB limit.".format(FILE_SIZE_LIMIT / 1024)
                return

            # Get history directory
            file_name = os.path.basename(file_path)
            history_dir = get_filedir(file_path)
            if not os.path.exists(history_dir):
                # Create directory structure
                os.makedirs(history_dir)

            # Get history files
            os.chdir(history_dir)
            history_files = glob.glob("*" + file_name)
            history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

            # Skip if no changes
            if history_files:
                if filecmp.cmp(file_path, os.path.join(history_dir, history_files[0])):
                    return

            # Store history
            shutil.copyfile(file_path, os.path.join(history_dir, "{0}.{1}".
                format(dt.now().strftime("%b.%d.%Y_%H.%M.%S"), file_name)))

            # Remove old files
            for file in history_files[HISTORY_LIMIT - 1:]:  # -1 as we just added a new file
                os.remove(file)

        # Process in a thread
        t = Thread(target=run, args=(view.file_name(),))
        t.start()


class HistoryOpen(sublime_plugin.TextCommand):

    def run(self, edit):
        # Get history directory
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_filedir(self.view.file_name())

        # Get history files
        try:
            os.chdir(history_dir)
        except OSError:
            sublime.status_message("No Local History Found")
            return
        history_files = glob.glob("*" + file_name)
        history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        if not history_files:
            sublime.status_message("No Local History Found")
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
        history_dir = get_filedir(self.view.file_name())

        # Get history files
        os.chdir(history_dir)
        history_files = glob.glob("*" + file_name)
        history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        # Skip the first one as its always identical
        history_files = history_files[1:]

        if not history_files:
            sublime.status_message("No Local History Found")
            return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Trigger save before comparing, if required!
            if self.view.is_dirty():
                self.view.run_command("save")

            # Show diff
            from_file = history_files[index]
            to_file = self.view.file_name()
            show_diff(self.view.window(), from_file, to_file)

        self.view.window().show_quick_panel(history_files, on_done)


class HistoryReplace(sublime_plugin.TextCommand):

    def run(self, edit):
        # Get history directory
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_filedir(self.view.file_name())

        # Get history files
        os.chdir(history_dir)
        history_files = glob.glob("*" + file_name)
        history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        # Skip the first one as its always identical
        history_files = history_files[1:]

        if not history_files:
            sublime.status_message("No Local History Found")
            return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Replace
            file = history_files[index]
            with open(file) as f:
                self.view.replace(edit, sublime.Region(0, self.view.size()), f.read())
            self.view.run_command("save")

        self.view.window().show_quick_panel(history_files, on_done)


class HistoryIncrementalDiff(sublime_plugin.TextCommand):

    def run(self, edit, **kwargs):
        # Get history directory
        file_name = os.path.basename(self.view.file_name())
        history_dir = get_filedir(self.view.file_name())

        # Get history files
        os.chdir(history_dir)
        history_files = glob.glob("*" + file_name)
        history_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        if len(history_files) < 2:
            sublime.status_message("No Incremental Diff Found")
            return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Selected the last file
            if index == len(history_files) - 1:
                sublime.status_message("No Incremental Diff Found")
                return

            # Show diff
            from_file = history_files[index + 1]
            to_file = history_files[index]
            show_diff(self.view.window(), from_file, to_file)

        self.view.window().show_quick_panel(history_files, on_done)


class HistoryDeleteAll(sublime_plugin.TextCommand):

    def run(self, edit):
        shutil.rmtree(HISTORY_PATH)
        sublime.status_message("All Local History Deleted")
