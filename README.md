# Local History

[![GitHub license](https://img.shields.io/github/license/vishr/local-history.svg?style=flat-square)](https://github.com/vishr/local-history/tree/master/LICENSE.md)
[![Total downloads via Package Control](https://img.shields.io/packagecontrol/dt/Local%20History.svg?style=flat-square)](https://packagecontrol.io/packages/Local%20History)
[![Monthly downloads via Package Control](https://img.shields.io/packagecontrol/dm/Local%20History.svg?style=flat-square)](https://packagecontrol.io/packages/Local%20History)


A [Sublime Text](https://www.sublimetext.com) package for maintaining a local history of files.

## Benefits

* Every time you modify a file, a copy of the old contents is kept in the local history when you:
  * open the file.
  * close the file.
  * and/or loose focus.
* Available functions are:
  * file comparison of the open file and any of its older versions from the history.
  * incremental diff view.
* Functions are available via:
  * the right-click context menu.
  * the `Local History: ...` commands from the command palette.
* `Local History` helps you out when you change or delete a file by accident.
* `Local History` can help you out when your workspace has a catastrophic problem or if you get disk errors that corrupt your workspace files.
* Each file revision is stored in a separate file (with full path):
	* inside the `~/.sublime/Local History/` folder of your home directory (`"portable": false`)
	* inside the `Sublime Text/Data/.sublime/Local History/` folder of your [Sublime Text](https://www.sublimetext.com) installation (`"portable": true`)

## Installation

* Via [Package Control](https://www.packagecontrol.io):
  * [Install Package Control](https://www.packagecontrol.io/installation)
  * Open the command palette (<kbd>Ctrl</kbd><kbd>⇧ Shift</kbd><kbd>P</kbd>)
  * Choose `Install Package`
  * Search for `Local History` and select to install.
* Clone the repo: `git clone git://github.com/vishr/local-history.git "Local History"` into your [Sublime Text](https://www.sublimetext.com) Packages directory.
  * via HTTPS: `https://github.com/vishr/local-history.git`
  * via SSH: `git@github.com:vishr/local-history.git`
* Download an archive file below, unpack it and then re-zip the contents of the `Local History` subdirectory. Rename `Local History.zip` to `Local History.sublime-package` and move it to your `Installed Packages` subdirectory of your [Sublime Text](https://www.sublimetext.com) installation:
  * current snapshot of master
    * [current snapshot of master as *.zip](https://github.com/vishr/local-history/archive/master.zip)
    * [current snapshot of master as *.tar.gz](https://github.com/vishr/local-history/archive/master.tar.gz)

## Usage

<img src="./docs/context-menu.png" alt="Context Menu" width="350" height="300">

* Functions are available via:
  * the right-click context menu.
  * the `Local History: ...` commands from the command palette.

<img src="./docs/tools-menu.png" alt="Tools Menu" width="400" height="320">

* To permanently delete all history files, choose `Tools > Local History > Delete Local History > Permanently delete all`

### Settings

```js
    "history_retention": 0, // number of days to keep files, 0 to disable deletion
    "format_timestamp": "%Y%m%d%H%M%S", // file_name-XXXXXXXX.file_extension
    "history_on_close": true,
    "history_on_focus_lost": false,
    "history_on_load": true,
    "portable": true, // save to 'Sublime Text/Data/.sublime/Local History/...' instead of '~/.sublime/Local History/...'
    "file_size_limit": 4194304 // 4 MB
```
