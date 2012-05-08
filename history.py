import sublime
import sublime_plugin
import os
from collections import defaultdict
import cPickle as pickle
from datetime import datetime as dt
import difflib
import filecmp
import shutil
from threading import Thread

#------------#
#   Config   #
#------------#
HISTORY_LIMIT = 50
FILE_SIZE_LIMIT = 256000  # bytes

# Paths
st2_path = os.path.dirname(sublime.packages_path())
history_path = os.path.join(st2_path, ".history")
map_path = os.path.join(history_path, ".map")


def create_history_dir_map():
    if not os.path.exists(history_path):
        os.makedirs(history_path)
        pickle.dump(defaultdict(list), open(map_path, "wb"), -1)
create_history_dir_map()


class HistorySave(sublime_plugin.EventListener):

    def on_post_save(self, view):

        def run(file_path):
            # Not saving
            if os.path.getsize(file_path) > FILE_SIZE_LIMIT:
                return

            file_name = os.path.basename(file_path)
            new_file_name = "{0}.{1}".format(dt.now().strftime("%b.%d.%Y.%H.%M.%S"), file_name)
            new_file_path = os.path.join(history_path, new_file_name)

            # Load history map
            with open(map_path, "rb") as map:
                history_map = pickle.load(map)
                history_list = history_map[file_path]

            # Skip if no changes
            if history_list:
                if filecmp.cmp(file_path, os.path.join(history_path, history_list[0])):
                    return

            # Get content
            with open(file_path, "r") as f:
                content = f.read()
                f.seek(0)
                to_content = f.readlines()

            # Store history
            with open(new_file_path, "w") as f:
                f.write(content)

            # Save a diff from previous version
            if len(history_list) >= 1:
                from_file = history_list[0]
                from_file_path = os.path.join(history_path, from_file)
                with open(from_file_path, "r") as f:
                    from_content = f.readlines()
                diff = difflib.unified_diff(from_content, to_content, from_file, new_file_name)
                diff_file_path = "{0}.diff".format(from_file_path)
                with open(diff_file_path, "w") as f:
                    f.write("".join(diff))

            with open(map_path, "wb") as map:
                # Add reference to map
                history_list.insert(0, new_file_name)

                # Remove old files
                for file in history_list[HISTORY_LIMIT + 1:]:
                    os.remove(os.path.join(history_path, file))
                # Remove reference from map
                del history_list[HISTORY_LIMIT + 1:]

                # Dump history map
                pickle.dump(history_map, map, -1)

        # Process in a thread
        t = Thread(target=run, args=(view.file_name(),))
        t.start()


class HistoryOpen(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch history
        with open(map_path, "rb") as map:
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
            self.view.window().open_file(os.path.join(history_path, files[index]))

        self.view.window().show_quick_panel(files, on_done)


class HistoryCompare(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch history
        with open(map_path, "rb") as map:
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
            from_file_path = os.path.join(history_path, from_file)
            with open(from_file_path, "r") as f:
                from_content = f.readlines()

            # To
            file_path = self.view.file_name()
            to_file = os.path.basename(file_path)
            with open(file_path, "r") as f:
                to_content = f.readlines()

            # Compare and show diff
            diff = difflib.unified_diff(from_content, to_content, from_file, to_file)
            self.show_diff("".join(diff))

        self.view.window().show_quick_panel(files, on_done)

    def show_diff(self, diff):
        panel = self.view.window().new_file()
        panel.set_scratch(True)
        panel.set_syntax_file("Packages/Diff/Diff.tmLanguage")
        panel_edit = panel.begin_edit()
        panel.insert(panel_edit, 0, diff)
        panel.end_edit(panel_edit)


class HistoryReplace(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch history
        with open(map_path, "rb") as map:
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
            file_path = os.path.join(history_path, file)
            with open(file_path, "r") as f:
                self.view.replace(edit, sublime.Region(0, self.view.size()), f.read())
            self.view.run_command("save")

        self.view.window().show_quick_panel(files, on_done)


class HistoryIncrementalDiff(sublime_plugin.TextCommand):

    def run(self, edit, **kwargs):
        with open(map_path, "rb") as map:
            history_map = pickle.load(map)
            history_list = history_map[self.view.file_name()]
            if len(history_list) < 2:
                sublime.status_message("No Incremental Diff Found")
                return
            diff_files = ["{0}.diff".format(file) for file in history_list[1:]]

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Open
            view = self.view.window().open_file(os.path.join(history_path, diff_files[index]), sublime.TRANSIENT)
            view.set_read_only(True)

        self.view.window().show_quick_panel(diff_files, on_done)
        # diff_file = "{0}.diff".format(history_list[self.index])
        # diff_file_path = os.path.join(history_path, diff_file)
        # self.view.window().open_file(diff_file_path, sublime.TRANSIENT)


class HistoryDeleteAll(sublime_plugin.TextCommand):

    def run(self, edit):
        shutil.rmtree(history_path)
        create_history_dir_map()
        sublime.status_message("All Local History Deleted")
