# finder

Python application to search files after indexing them. Similar to voidtool's Everything, but much simpler. Supports partial match and some filterings:

`<n>:` Limit search to specified database

`docx:` Limit search to documents (docx, doc)

`zip:` Limit search to compressed files (zip, 7z)

`exe:` Limit search to executable files (exe, com, bat, cmd)


## Warnings & Known Issues
- Does not support regexp

## Installation
requires Python 3 
Steps:
1. `git clone` this repository or download the files under src.
2. in the install directory run `pip3 install -r requirements.txt`
3. Run it with the batch file provided if using Anaconda or with `pythonw finder.pyw` 

## How it works:

The script indexes the filesystem using os.walk and creates a compressed database.
The paths to index are specified in the finder.ini file under the `[paths]` section, with `<n>=<path>` syntax.



### Screenshot
<img src="/img/finder.png" alt="Finder screenshot" width="600"/>



