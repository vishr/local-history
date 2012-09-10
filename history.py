import sublime
import sublime_plugin
import os
import platform
from collections import defaultdict
import cPickle as pickle
from datetime import datetime as dt
import difflib
import filecmp
import shutil
from threading import Thread

#--------------#
#   Settings   #
#--------------#
settings = sublime.load_settings("LocalHistory.sublime-settings")
history_location = settings.get("history_location", "~")
if history_location == "~":
    history_location = os.path.expanduser("~")
HISTORY_PATH = os.path.join(history_location, ".sublime", "history")
MAP_PATH = os.path.join(HISTORY_PATH, ".map")
HISTORY_LIMIT = settings.get("history_limit", 50)
FILE_SIZE_LIMIT = settings.get("file_size_limit", 262144)


def create_history_dir_map():
    if not os.path.exists(HISTORY_PATH):
        os.makedirs(HISTORY_PATH)
        pickle.dump(defaultdict(list), open(MAP_PATH, "wb"), -1)
create_history_dir_map()


def show_diff(window, diff):
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
            # Return if file exceeds the limit
            if os.path.getsize(file_path) > FILE_SIZE_LIMIT:
                print "WARNING: Local History did not save a copy of this file because it has exceeded {0}KB.".format(FILE_SIZE_LIMIT / 1024)
                return

            file_name = os.path.basename(file_path)
            newfile_name = "{0}.{1}".format(dt.now().strftime("%b.%d.%Y.%H.%M.%S"), file_name)
            newfile_dir = get_filedir(file_path)
            newfile_path = os.path.join(newfile_dir, newfile_name)

            # Load history map
            with open(MAP_PATH, "rb") as map:
                history_map = pickle.load(map)
                history_list = history_map[file_path]

            # Skip if no changes
            if history_list:
                if filecmp.cmp(file_path, os.path.join(newfile_dir, history_list[0])):
                    return

            # Store history
            if not os.path.exists(newfile_dir):
                os.makedirs(newfile_dir)  # Create directory structure
            shutil.copyfile(file_path, newfile_path)

            # Add reference to map
            history_list.insert(0, newfile_name)

            # Remove old files
            for file in history_list[HISTORY_LIMIT:]:
                os.remove(os.path.join(newfile_dir, file))

            # Remove old references from map
            del history_list[HISTORY_LIMIT:]

            with open(MAP_PATH, "wb") as map:
                # Dump history map
                pickle.dump(history_map, map, -1)

        # Process in a thread
        t = Thread(target=run, args=(view.file_name(),))
        t.start()


class HistoryOpen(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch history
        with open(MAP_PATH, "rb") as map:
            history_map = pickle.load(map)
            history_list = history_map[self.view.file_name()]
            # Skip the first one as its always identical
            files = history_list[1:]
            if not files:
                sublime.status_message("No Local History Found")
                return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Open
            file_dir = get_filedir(self.view.file_name())
            self.view.window().open_file(os.path.join(file_dir, files[index]))

        self.view.window().show_quick_panel(files, on_done)


class HistoryCompare(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch history
        with open(MAP_PATH, "rb") as map:
            history_map = pickle.load(map)
            history_list = history_map[self.view.file_name()]
            # Skip the first one as its always identical
            files = history_list[1:]
            if not files:
                sublime.status_message("No Local History Found")
                return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Trigger save before comparing, if required!
            if self.view.is_dirty():
                self.view.run_command("save")

            # From
            from_file = files[index]
            file_dir = get_filedir(self.view.file_name())
            from_file_path = os.path.join(file_dir, from_file)
            with open(from_file_path, "r") as f:
                from_content = f.readlines()

            # To
            file_path = self.view.file_name()
            to_file = os.path.basename(file_path)
            with open(file_path, "r") as f:
                to_content = f.readlines()

            # Compare and show diff
            diff = difflib.unified_diff(from_content, to_content, from_file, to_file)
            diff = [d.decode("utf8") for d in diff]
            show_diff(self.view.window(), "".join(diff))

        self.view.window().show_quick_panel(files, on_done)


class HistoryReplace(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch history
        with open(MAP_PATH, "rb") as map:
            history_map = pickle.load(map)
            history_list = history_map[self.view.file_name()]
            # Skip the first one as its always identical
            files = history_list[1:]
            if not files:
                sublime.status_message("No Local History Found")
                return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Replace
            file = files[index]
            file_dir = get_filedir(self.view.file_name())
            file_path = os.path.join(file_dir, file)
            with open(file_path, "r") as f:
                self.view.replace(edit, sublime.Region(0, self.view.size()), f.read())
            self.view.run_command("save")

        self.view.window().show_quick_panel(files, on_done)


class HistoryIncrementalDiff(sublime_plugin.TextCommand):

    def run(self, edit, **kwargs):
        with open(MAP_PATH, "rb") as map:
            history_map = pickle.load(map)
            history_list = history_map[self.view.file_name()]
            if len(history_list) < 2:
                sublime.status_message("No Incremental Diff Found")
                return
            files = history_list[:-1]

        def on_done(index):
            # Escape
            if index == -1:
                return

            if len(history_list) >= 1:
                from_file = history_list[index + 1]
                file_dir = get_filedir(self.view.file_name())
                from_file_path = os.path.join(file_dir, from_file)
                with open(from_file_path, "r") as f:
                    from_content = f.readlines()

                to_file = history_list[index]
                file_dir = get_filedir(self.view.file_name())
                to_file_path = os.path.join(file_dir, to_file)
                with open(to_file_path, "r") as f:
                    to_content = f.readlines()
                diff = difflib.unified_diff(from_content, to_content, from_file, to_file)
                diff = [d.decode("utf8") for d in diff]
                show_diff(self.view.window(), "".join(diff))

        self.view.window().show_quick_panel(files, on_done)


class HistoryDeleteAll(sublime_plugin.TextCommand):

    def run(self, edit):
        shutil.rmtree(HISTORY_PATH)
        create_history_dir_map()
        sublime.status_message("All Local History Deleted")
