# moodle-backup-extract

This project's purpose is to assist with extracting useful, human-readable content from a backup of a Moodle site for a course you may have taught. Before using the utilities here, create a backup of your Moodle site by clicking the gear in the upper left, selecting "Backup," clicking "Got to last step," then creating the backup. After doing this, download your backup. (It will be the top one in the list of backups.) This will download a file with a .mbz extension. This is actually just a ZIP file. You need to extract its contents into a directory somewhere on your computer. If you are unable to do so directly from the MBZ file, rename the extension to .zip. These instructions can also be found [here](http://www.reades.com/2012/11/29/mb-archives/).

Once you have extracted your backup into a directory, you can run

`python3 moodle_backup_organize.py source [dest] [--reset]`

where `source` is the directory containing your extracted backup and `dest` is the directory where you want the usable content extracted from your backup to reside. `dest` is optional; the default is for the source and destination to be the same. The script will extract all of your files and name them their correct names, placing them in a subdirectory of `dest` named `content`. It will also extract HTML versions of assignments, pages, folders, URLs, quizzes, and resources from your site, storing them in a subdirectory of `dest` named `html`.

It also creates a file called `index.html` in your `html` directory containing organized links to the other HTML files created.

If you pass the optional flag `--reset` as a final argument, it will delete existing `content` and `html` directories before it runs. Otherwise, it will treat existing files that it would create as already present, except for `index.html` which it always re-creates.

## Dependencies

This project requires Python 3.8 or higher, and you are strongly encouraged to have the module `pathvalidate` installed to avoid unwanted transcription failures. It can be installed via

`pip3 install pathvalidate`
