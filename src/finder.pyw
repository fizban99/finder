# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, StringVar, messagebox
import threading
import os
import time
import tables as tb
from unidecode import unidecode
import numpy as np
import locale
import screeninfo
from queue import Queue
import datetime
import configparser
from functools import partial
from indexer import create_index
import sys
import subprocess
from time import time
from pyroaring import BitMap


# Custom event names
TREEUPDATE_EVENT = "<<CustomTreeUpdate>>"
CONTEXTMENU_EVENT = "<<CustomContextMenu>>"
REINDEX_EVENT = "<<CustomReindex>>"

# Set the locale to the user's default setting
locale.setlocale(locale.LC_ALL, '')


def to_integer(value):
    try:
        return int(str(value).replace(".",""))
    except ValueError:
        return -1



def center_window(window, w, h):
    # place the window on the biggest monitor
    monitors = screeninfo.get_monitors()
    sw= 0 
    sw_mm = 0
    for m in monitors:
        if m.width_mm > sw_mm:
            sw = m.width
            sh = m.height
            x = m.x
            y = m.y
            sw_mm = m.width_mm
    a, b = x + (sw - w) / 2, y + (sh-h) / 2 
    window.geometry('%sx%s+%d+%d'%(w,h,a,b))


def binary_search(table, key, value, left = 0, leftmost=True):
    right = table.nrows - 1
    result = None

    while left <= right:
        mid = (left + right) // 2
        mid_value = table[mid][key]

        if mid_value == value:
            result = mid
            if leftmost:
                right = mid - 1
            else:
                left = mid + 1
        elif mid_value < value:
            if not leftmost:
                result = mid
            left = mid + 1
        else:
            if leftmost:
                result = mid
            right = mid - 1

    return result



class StatusBar(tk.Frame):
    def __init__(self, master):
        tk.Frame.__init__(self, master)
        self.label_text = tk.StringVar()
        self.label = tk.Label(self, bd=1, relief=tk.SUNKEN, anchor=tk.W, textvariable=self.label_text)
        self.label.pack(fill=tk.X)

    def set(self, text):
        self.label_text.set(text)
        self.label.update_idletasks()


def update_scrollbar(treeview, scrollbar):
    # Determine if the contents exceed the visible area
    children = treeview.get_children()
    num_items = len(children)
    
    if num_items > 0:
        first_visible_item = treeview.yview()[0]
        last_visible_item = treeview.yview()[1]
        visible_fraction = last_visible_item - first_visible_item

        if visible_fraction < 1.0:
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            scrollbar.pack_forget()
    else:
        scrollbar.pack_forget()

class App:
    def __init__(self, root):
        # avoid flashing an empty window at start
        root.withdraw()
        self.root = root
        self.app_path = os.path.dirname(os.path.abspath(__file__))
        
        self.root.title("Finder")
        icon_file = self.app_path + "/img/search.ico"
        self.root.iconbitmap(icon_file)
        # Set Windows taskbar icon
        self._set_icon(icon_file)
        
        self.last_query = ""
        self.match_count = 0

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Create a ConfigParser object
        config = configparser.ConfigParser()
                
        # Read data from the INI file
        config.read(self.app_path + '/finder.ini')
        # Access data from the INI file
        n=0
        self.walk_paths = []
        while True:
            try:
                self.walk_paths.append(config.get('Paths', f'{n}'))
            except (configparser.NoOptionError, configparser.NoSectionError):
                break
            n += 1
        if len(self.walk_paths)==0:
            self.walk_paths = ["C:\\"]
        
        # Create a menu bar
        self.menubar = tk.Menu(self.root)
        self.filemenu = tk.Menu(self.menubar, tearoff=0)
        # Create the "Reindex" menu and add it to the top-level menu
        self.reindex_menu = tk.Menu(self.filemenu, tearoff=0)
        self.filemenu.add_cascade(label="Reindex", menu=self.reindex_menu)
        for n, p in enumerate(self.walk_paths):
            self.reindex_menu.add_command(label=f"{n}: {p}", command=partial(self.reindex, [n,]))
        self.filemenu.add_separator()
        self.filemenu.add_command(label="Exit", command=self.on_close)
        self.menubar.add_cascade(label="File", menu=self.filemenu)
        self.root.config(menu=self.menubar)

        # Create an Entry widget at the top
        self.entry_var = StringVar()
        self.entry = tk.Entry(self.root, textvariable=self.entry_var)
        self.entry.pack(fill=tk.X,pady=2, padx=2)
        self.entry.focus_set()
    
        self.frame = ttk.Frame(root)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        self.treeview = ttk.Treeview(self.frame)
        self.treeview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Create a vertical scrollbar and connect it to the treeview
        self.scrollbar = ttk.Scrollbar(self.frame, orient='vertical', command=self.treeview.yview)
        # self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        
        # Configure the treeview to update the scrollbar's position
        self.treeview.configure(yscrollcommand=self.scrollbar.set)


        # Configure the TreeView widget as a list view with Name, Location, Size, and Modification Date columns
        self.treeview["columns"] = ("Location", "Size", "Modification Date")
        self.treeview.column("#0", width=400, stretch=tk.NO)
        self.treeview.column("Location", anchor="w", width=400)
        self.treeview.column("Size", anchor="e", width=100)
        self.treeview.column("Modification Date", anchor="center", width=100)

        self.treeview.heading("#0", text="Name  ", 
                              command=lambda: self.treeview_sort_column("#0"))
        self.treeview.heading("Location", text="Location  ", 
                              command=lambda: self.treeview_sort_column( "Location"))
        self.treeview.heading("Size", text="Size  ", 
                              command=lambda: self.treeview_sort_column( "Size"))
        self.treeview.heading("Modification Date", 
                              text="Modification Date  ", 
                              command=lambda: self.treeview_sort_column( "Modification Date"))

        # Load folder icon (assuming folder_icon.gif is in the same directory as your script)
        self.folder_icon = tk.PhotoImage(file=self.app_path + '/img/folder.png')      
        self.document_icon = tk.PhotoImage(file=self.app_path + '/img/file.png')      


        # Create a StatusBar widget at the bottom
        self.statusbar = StatusBar(self.root)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

        # Create a context menu for the TreeView widget
        self.treeview_context_menu = tk.Menu(self.root, tearoff=0)
        self.treeview_context_menu.add_command(label="Open", command=self.on_double_click)
        self.treeview_context_menu.add_command(label="Go to folder", command=self.menu_go_to_folder)
        self.treeview_context_menu.add_command(label="Open Command Prompt here", command=self.menu_cmd_here)
        self.treeview_context_menu.add_command(label="Copy full path", command=self.menu_copy_path)

        # Bind the right-click event to display the context menu
        self.treeview.bind("<Button-3>", self.on_right_mouse_click)
        
        # Bind the double-click event to default os
        self.treeview.bind('<Double-1>', self.on_double_click)

        # Make the app resizable
        self.root.resizable(True, True)
        

        
        # Bind the key release event to the on_key_press function
        self.entry.bind("<Key>", lambda event: self.on_key_press(event))
        
        # Initially update the scrollbar
        update_scrollbar(self.treeview, self.scrollbar)
        
        # Update scrollbar when the treeview is resized
        self.treeview.bind('<Configure>', lambda event: update_scrollbar(self.treeview, self.scrollbar))

        # this is to try to reduce a weird problem when right mouse clicking and 
        # automatically selecting the first option
        self.root.bind(CONTEXTMENU_EVENT, self.display_treeview_context_menu)
                
        # Bind the custom event to the window to update the treeview 
        # once the get_matches thread retrieves the result
        # since the tkinter interface should be updated from the main thread
        # (it is very slow updating it from a separate thread)
        self.root.bind(TREEUPDATE_EVENT, self.update_treeview)
        
        self.root.bind(REINDEX_EVENT, self.check_stores)
        self.root.event_generate(REINDEX_EVENT, when="tail")
        
        center_window(root, 1024, 300)
        # show window
        root.deiconify()  
        root.update()
        


    def on_close(self):
        for s in self.stores:
            if s is not None:
                s.close()
        self.root.destroy()


    def _set_icon(self, icon_file):
        if sys.platform == 'win32':
            # https://stackoverflow.com/questions/1551605/how-to-set-applications-taskbar-icon-in-windows-7/1552105
            import ctypes
            myappid = u'fizban99.finder.1' # arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        self.root.title("Finder")
        self.root.iconbitmap(icon_file)


    def on_double_click(self, event=None):
        treeview = self.treeview
        selected_item = treeview.selection()
    
        if selected_item:
            file_path = treeview.item(selected_item)['values'][0] + "\\" + treeview.item(selected_item)["text"]
            os.startfile(file_path)

    def on_key_press(self, event):
        event.widget.after(0, self.on_key_press_after)
        
    def on_key_press_after(self):
        current_query = self.entry.get()
        if current_query != self.last_query:
            self.last_query = current_query
            self.queue.put(current_query)


    def get_matches(self):
        while True:
          # wait for an item
          query = self.queue.get()
          
          # skip all until the last
          while not self.queue.empty():
              query = self.queue.get()

          self.match_count = 0
          parts = query.split(":")
          drive = None
          if len(parts) > 1:
              if parts[0].isdigit():
                  drive = int(parts[0])
                  query = query[len(parts[0])+1:]
          
          self.matches = []
          for n, store in enumerate(self.stores):                
              if drive is None or drive == n:
                  self.matches.extend( self.find_matches(query, store))
              
          self.root.event_generate(TREEUPDATE_EVENT, when="tail")
        

    def update_treeview(self, event):
        self.treeview.delete(*self.treeview.get_children())
       
        
        for match in self.matches:
            if match[2]=="-":
                icon = self.folder_icon
            else:
                icon = self.document_icon
            self.treeview.insert("", tk.END, text = match[0], image=icon ,values=[match[1],match[2], match[3]])
        
        if self.match_count > len(self.matches):
            note = f" (displaying only {len(self.matches)})"
        else:
            note = ""
        self.statusbar.set(locale.format_string("%d", self.match_count, grouping=True) + " objects" + note)
     
        self.treeview.update_idletasks()
        update_scrollbar(self.treeview, self.scrollbar)



    def on_right_mouse_click(self, event):
        # Select on right-mouse click
        if not self.treeview_context_menu.winfo_viewable():
            item = self.treeview.identify_row(event.y)
            
            if item and self.treeview.selection() != (item,):
                  self.treeview.selection_set(item)
                  
        self.context_x = event.x_root
        self.context_y = event.y_root
        self.root.event_generate(CONTEXTMENU_EVENT, when="tail")

    
    def display_treeview_context_menu(self, event):
        
        # Display the context menu for the TreeView widget
        try:
            self.treeview_context_menu.tk_popup(self.context_x, self.context_y, 0)
            self.treeview_context_menu.update_idletasks()

        finally:
            self.treeview_context_menu.grab_release()


    
    def find_matches(self, text, store):
        max_files = 50
        if self.match_count >= max_files:
            max_files = 0 
        else:
            max_files = max_files - self.match_count
         
            
        if text!="":
            node_type = ""
            if ":" in text:
                text = text.split(":")
                node_type, text = text[0], text[1]
            text=unidecode(text.lower())
            if len(text)==0:
                return []
            stext = text.split()
        
            prev_file_ids = None
            for text in stext:
                text = text.encode("utf8")
                
                text2=text + b'\x7f'
                condition = ""
                
                ext_map = {"doc": 2,
                           "docx":2,
                           "zip": 3,
                           "7z": 3,
                           "exe": 4,
                           "com": 4,
                           "bat": 4,
                           "cmd": 4,
                           }
                
                if node_type == "file":
                    condition = "(type>0)"
                elif node_type == "folder":
                    condition = "(type==0)"
                elif node_type in ext_map:
                    condition = f"(type=={ext_map[node_type]})"
                
                entry_id_start = binary_search(store.root.entries, "partial_entry", text)
                if entry_id_start is None:
                    return []
                index_id_start = binary_search(store.root.index, "entry_id", entry_id_start)
                # print(time()-st)
                # Return if no matches found unless there is one single match 
                # (because of the optimization of not having all the text for single matches)
                if text != store.root.entries[entry_id_start]["partial_entry"][:len(text)]:
                    if entry_id_start == 0:
                        return
                    entry_id_start -= 1
                    index_id_start = binary_search(store.root.index, "entry_id", entry_id_start)
                    node_id = store.root.index[index_id_start]["file_id"]
                    node_text = store.root.nodes[node_id]["entry"]
                    node_text = unidecode(node_text.decode("utf8").lower()).encode("utf8")
                    # print(node_text)
                    if text not in node_text:
                        return[]
                
                entry_id_end = binary_search(store.root.entries, "partial_entry", text2, entry_id_start)
                # print(entry_id_start, entry_id_end)
                if entry_id_end is None:
                    entry_id_end = store.root.entries.nrows
                
    
                index_id_stop = binary_search(store.root.index, "entry_id", entry_id_end, index_id_start, leftmost=True)+1
                # print(entry_id_end, store.root.index[index_id_stop-1]["entry_id"])
                # print(index_id_start, index_id_stop)
                if index_id_stop is None:
                    index_id_stop = store.root.index.nrows
                elif index_id_stop == index_id_start+1:
                    index_id_stop +=1
                # if index_id_stop -index_id_start <10:
                #         print(store.root.index[index_id_start:index_id_stop])
                if condition == "":
                    file_ids = np.unique(store.root.index.read(start=index_id_start, stop = index_id_stop-1, field="file_id" ))
                else:
                    file_ids = np.unique(store.root.index.read_where(condition=condition, start=index_id_start, stop = index_id_stop-1, field="file_id" ))
                

                if len(stext) >0:
                    if prev_file_ids is None:
                        prev_file_ids = BitMap()
                        prev_file_ids.update(file_ids)
                    else:
                        bfile_ids = BitMap()
                        bfile_ids.update(file_ids)
                        prev_file_ids = prev_file_ids.intersection(bfile_ids)
            self.match_count += len(prev_file_ids)
                        
        else:
            self.match_count += len(store.root.nodes)
            prev_file_ids = range(0,max_files)

        self.statusbar.set(locale.format_string("%d", self.match_count, grouping=True) + " objects. Retrieving details...")
        file_ids = prev_file_ids
        max_files = min(max_files, store.root.nodes.nrows)
        matches = []
        for file_id in file_ids[:max_files]:
           node = store.root.nodes[file_id]
           match = node["entry"].decode("utf8")
           file_path = store.root.paths[node["path_id"]]["path"].decode("utf8")  + "\\" + match
           if os.path.exists(file_path):
               modification_date = datetime.datetime.fromtimestamp( os.path.getmtime(file_path))
               modification_date = modification_date.strftime("%Y-%m-%d %H:%M")
           else:
               modification_date = "????"
           if node["type"] == 0:             
               size = "-"
           else:
               if os.path.exists(file_path):
                   size = locale.format_string("%d", os.path.getsize(file_path), grouping=True)
               else:
                   size = "????"
           match = (match, store.root.paths[node["path_id"]]["path"].decode("utf8"), size, modification_date )
           matches.append(match)
           # If user types before finishing, exit
           if not self.queue.empty():
               return []

        
        return matches


    def reindex_process(self, n_list):
        for n in n_list:
            create_index(self.app_path + f"/data/{n}.h5", self.walk_paths[n], self.statusbar)
        self.root.attributes('-disabled', False)
        self.entry.configure(state='normal')
        for n in n_list:
            self.stores[n] = tb.open_file(self.app_path + f"/data/{n}.h5", "r") 
        
        self.queue.put("")   


    def reindex(self, n_list, confirm = True):
        if confirm:
            response = messagebox.askyesno(title="Confirmation", message=f"Do you want to reindex the path '{self.walk_paths[n_list[0]]}'?")
        else:
            response = True
        if response:
            for n in n_list:
               if self.stores[n] is not None:
                    self.stores[n].close()
            self.root.attributes('-disabled', True)
            self.entry.configure(state='disabled')
            self.indexer_thread = threading.Thread(target=self.reindex_process, args=(n_list,))
            self.indexer_thread.daemon = True
            self.indexer_thread.start()
        else:
            return


    def check_stores(self, event):

        missing_dbs = []
        self.stores = []
        for idx, path in enumerate(self.walk_paths):
            
            dbpath = self.app_path + f"/data/{idx}.h5"
            if os.path.exists(dbpath):
                self.stores.append(tb.open_file(dbpath, "r"))
            else:
                missing_dbs.append((idx,path))
                self.stores.append(None)
        
        # Set up queue for pipe
        self.queue = Queue()

        # Set up threading
        self.update_thread = threading.Thread(target=self.get_matches)
        self.update_thread.start()


        if len(missing_dbs) > 0:
            response = messagebox.askyesno(title="Confirmation", 
                                           message=f"Some databases were not found. {missing_dbs}"
                                           "\nDo you want to recreate them?\n"
                                           "If not, the application will exit.")
            if response:
                self.reindex([db[0] for db in missing_dbs], confirm=False)
                
            else:
                self.root.quit()
                self.root.destroy()
        else:
            self.queue.put("")            


    def reset_sort_icon(self, column):
        for col in ("#0", "Location", "Size", "Modification Date"):
            if col != column:
                self.treeview.heading(col, text=self.treeview.heading(col, "text").rstrip("▲▼"))



    def treeview_sort_column(self, column):
        self.reset_sort_icon(column)
        
        data = [(self.treeview.item(child), child) for child in self.treeview.get_children("")]
        if column == "#0":
            data.sort(key=lambda x: x[0]["text"])
        elif column == "Size":
            col_index = self.treeview["columns"].index(column)
            data.sort(key=lambda x: to_integer(x[0]["values"][col_index]))
        else:
            col_index = self.treeview["columns"].index(column)
            data.sort(key=lambda x: x[0]["values"][col_index])

        for index, (_, child) in enumerate(data):
            self.treeview.move(child, "", index)

        if self.treeview.heading(column, "text")[-1] == "▲":
            self.treeview.heading(column, text=self.treeview.heading(column, "text")[:-1] + "▼")
            data.reverse()
            for index, (_, child) in enumerate(data):
                self.treeview.move(child, "", index)
        elif self.treeview.heading(column, "text")[-1] == "▼":
            self.treeview.heading(column, text=self.treeview.heading(column, "text")[:-1] + "▲")
        else:
            self.treeview.heading(column, text=self.treeview.heading(column, "text") + "▲")


    def get_item_path(self, selected_item, use_folder=True):
        treeview = self.treeview
        if treeview.item(selected_item)['values'][1]=="-" or not use_folder:
            # if it is a folder
            parent = treeview.item(selected_item)['values'][0]
            if parent[-1] != "\\":
                parent += "\\"
            path = parent + treeview.item(selected_item)["text"]
        else:
            path = treeview.item(selected_item)['values'][0]         
        return path



    def menu_go_to_folder(self):
        if sys.platform == 'win32':
            treeview = self.treeview
            selected_item = treeview.selection()
    
            if selected_item:
                path = self.get_item_path(selected_item)
                print(path)
                subprocess.run(['explorer', path])
    
    
    def menu_cmd_here(self):
        if sys.platform == 'win32':
            treeview = self.treeview
            selected_item = treeview.selection()
    
            if selected_item:
                path = self.get_item_path(selected_item)
                os.startfile(path, 'cmd')
    
    
    def menu_copy_path(self):
        treeview = self.treeview
        selected_item = treeview.selection()

        if selected_item:
            path = self.get_item_path(selected_item, use_folder=False)     
            self.root.clipboard_append(path)



if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
