# Local History
#### A Sublime Text 2 plugin for maintaining local history of files

##Benefits

* Every time you modify a file, a copy of the old contents is kept in the local history.
* At any time, you can compare or replace a file with any older version from the history.
* View incremental diff of any file form history.
* It can help you out when you change or delete a file by accident.
* The history can also help you out when your workspace has a catastrophic problem or if you get disk errors that corrupt your workspace files.
* Each file revision is stored in a separate file inside the `history` folder.
e.g., `/Users/vrana/.sublime/history/foo/bar/hello.23.2012.10.10.34.history.py`

## Installation
**With the Package Control plugin:** The easiest way to install this plugin is through [Package Control](http://wbond.net/sublime_packages/package_control)

**Without Git:** Download the latest source zip from [github](https://github.com/vishr/local-history/zipball/master) and extract the files to your Sublime Text "Packages" directory, into a new directory named `Local History`.

**With Git:** Clone the repository in your Sublime Text "Packages" directory:

    git clone git@github.com:vishr/local-history.git "Local History"

The "Packages" directory location:

* OS X:
    `~/Library/Application Support/Sublime Text 2/Packages/`
* Linux:
    `~/.Sublime Text 2/Packages/`
* Windows:
    `%APPDATA%/Sublime Text 2/Packages/`

## Usage
![Open / Compare / Replace / Incremental Diff](http://i.imgur.com/qeoGl.png)

![Open / Compare / Replace / Incremental Diff](http://i.imgur.com/ADMgy.png)

![Delete All](http://i.imgur.com/nUlx8.png)


## Caveats

* Tested only on OS X and Windows
* As this plugin is continuously evolving, please delete the history and reinstall the plugin incase you face any problems.
