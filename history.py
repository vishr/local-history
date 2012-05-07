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

# Paths
plugin_path = os.path.join(sublime.packages_path(), "Local History")
history_path = os.path.join(plugin_path, ".history")
map_path = os.path.join(history_path, ".map")


def create_history_dir_map():
    if not os.path.exists(history_path):
        os.makedirs(history_path)
        pickle.dump(defaultdict(list), open(map_path, "wb"), -1)
create_history_dir_map()


class HistorySave(sublime_plugin.EventListener):

    def on_post_save(self, view):

        def run(file_path):
            file_name = os.path.basename(file_path)
            new_file_name = "{0}.{1}".format(dt.now().strftime("%b.%d.%Y.%H.%M.%S"), file_name)
            new_file_path = os.path.join(history_path, new_file_name)

            # Load history map
            with open(map_path, "rb") as map:
                history_map = pickle.load(map)

            # Skip if no changes
            if history_map[file_path]:
                if filecmp.cmp(file_path, os.path.join(history_path, history_map[file_path][0])):
                    return

            # Get content
            with open(file_path, "r") as f:
                content = f.read()

            # Store history
            with open(new_file_path, "w") as f:
                f.write(content)

            # Dump history map
            with open(map_path, "wb") as map:
                history_map[file_path].insert(0, new_file_name)
                pickle.dump(history_map, map, -1)

                # Remove old files
                for file in history_map[file_path][HISTORY_LIMIT + 1:]:
                    os.remove(os.path.join(history_path, file))
                # Remove reference from the map
                del history_map[file_path][HISTORY_LIMIT + 1:]

        # Process in a thread
<<<<<<< HEAD
        t = Thread(target=run, args=(view.file_name(),))
=======
        t = Thread(target=run, args=(view.file_name(), view.substr(sublime.Region(0, view.size()))))
>>>>>>> f255be701ee78c855c5683a043b6603d07e99b81
        t.start()


class HistoryOpen(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch history
        with open(map_path, "rb") as map:
            history_map = pickle.load(map)
            # Skip the first one as its always identical
            files = history_map[self.view.file_name()][1:]
            if not files:
                sublime.status_message("No Local History")
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
            # Skip the first one as its always identical
            files = history_map[self.view.file_name()][1:]
            if not files:
                sublime.status_message("No Local History")
                return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Trigger save before comparing, if required!
            print self.view.is_dirty()
            if self.view.is_dirty():
                self.view.run_command("save")

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
            panel_edit = panel.begin_edit()
            panel.insert(panel_edit, 0, diff)
            panel.end_edit(panel_edit)
        else:
            sublime.status_message("No Difference")


class HistoryReplace(sublime_plugin.TextCommand):

    def run(self, edit):
        # Fetch history
        with open(map_path, "rb") as map:
            history_map = pickle.load(map)
            # Skip the first one as its always identical
            files = history_map[self.view.file_name()][1:]
            if not files:
                sublime.status_message("No Local History")
                return

        def on_done(index):
            # Escape
            if index == -1:
                return

            # Replace
            file = files[index]
            with open(os.path.join(history_path, file), "r") as f:
                self.view.replace(edit, sublime.Region(0, self.view.size()), f.read())
            self.view.run_command("save")

        self.view.window().show_quick_panel(files, on_done)


class HistoryDeleteAll(sublime_plugin.TextCommand):

    def run(self, edit):
        shutil.rmtree(history_path)
        create_history_dir_map()
        sublime.status_message("All Local History Deleted")
