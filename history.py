import sublime
import sublime_plugin
import os
from collections import defaultdict
import cPickle as pickle
from datetime import datetime as dt
import difflib

# Setup
plugin_path = os.path.join(sublime.packages_path(), "LocalHistory")
store_path = os.path.join(plugin_path, ".store")
history_path = os.path.join(plugin_path, ".history")
# Create store
if not os.path.exists(store_path):
    pickle.dump(defaultdict(list), open(store_path, "wb"))
# Create history directory
if not os.path.exists(history_path):
    os.makedirs(history_path)


class LocalHistorySave(sublime_plugin.EventListener):

    def on_post_save(self, view):
        file_path = view.file_name()
        file_name = os.path.basename(file_path)
        new_file_name = "{0} at {1}".format(file_name, dt.now().strftime("%b %d, %Y %H:%M:%S"))
        new_file_path = os.path.join(history_path, new_file_name)

        with open(file_path, "r") as f:
            content = f.read()

        with open(new_file_path, "w") as f:
            f.write(content)

        # Load store
        with open(store_path, "rb") as store:
            history = pickle.load(store)

        # Dump store
        with open(store_path, "wb") as store:
            # Truncate old items
            del history[file_path][51:]

            history[file_path].insert(0, new_file_name)
            pickle.dump(history, store)


class LocalHistoryMenu(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch local history
        with open(store_path, "rb") as store:
            history = pickle.load(store)
            files = history[self.view.file_name()]
            if not files:
                sublime.status_message("No Local History")
                return

        def on_done(index):
            # From
            from_file = files[index]
            with open(os.path.join(history_path, from_file), "r") as f:
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
        if diff:
            panel = self.view.window().new_file()
            panel.set_scratch(True)
            panel.set_syntax_file("Packages/Diff/Diff.tmLanguage")
            panel_edit = panel.begin_edit("diff")
            panel.insert(panel_edit, 0, diff)
            panel.end_edit(panel_edit)
        else:
            sublime.status_message("No Difference")


def clean_up():
    pass
