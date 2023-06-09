# finder

Python application to search files after indexing them. Similar to voidtool's Everything, since it shows results as you type, but much simpler, so it does not require Administrative privileges, but does not update the database in real time and currently only shows the first 50 matches. It has a relatively low memory footprint during normal operation, but indexing might require more memory. Supports partial match so if you type different pieces of text separated by space, the tool will retrieve the files that match all the partial matches (an AND of all the text pieces). Also supports some filterings:

`<n>:` Limit search to specified database

`docx:` Limit search to documents (docx, doc)

`zip:` Limit search to compressed files (zip, 7z)

`exe:` Limit search to executable files (exe, com, bat, cmd)


## Known Issues
- Does not support regexp or wildcards
- Matches only file and folder names, but not the full path
- Only the file/folder names are stored in the database. The dates and sizes are retrieved in real time, which can slow down the display of the results.
- The database is bigger than the one generated by Everything

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



