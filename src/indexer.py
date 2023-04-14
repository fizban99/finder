# -*- coding: utf-8 -*-
"""
Created on Sat Apr  1 12:28:46 2023

"""

import os
import tables as tb
from unidecode import unidecode
from collections import defaultdict
from pyroaring import BitMap
from numba import njit


@njit
def first_different_byte(byte_str1, byte_str2):
    length1, length2 = len(byte_str1), len(byte_str2)
    
    for i in range(min(length1, length2)):
        if byte_str1[i] != byte_str2[i]:
            return i
    
    if length1 != length2:
        return min(length1, length2)
    
    return None


def create_index(file_name, disk_path, label):
    paths_list=[]
    path_id = 0
    nodes_list = []
    max_entry_length = 0
    max_path_length = 0
    # Use os.walk() to list all files in the disk recursively
    label.set(f"Scanning folders and files under '{disk_path}'. This can take several minutes and the application may appear as not responding...")
    for root, folders, files in os.walk(disk_path):
        root = root.encode("utf8")
        paths_list.append((root,))
        if len(root) > max_path_length:
            max_path_length = len(root)
        for folder in folders:
            folder = folder.encode("utf8")
            nodes_list.append((folder, 0, path_id ))
            if len(folder) > max_entry_length:
                max_entry_length = len(folder)
    
        for file in files:
            file = file.encode("utf8")
            extension = file.split(b".")
            if len(extension) >0:
                extension = extension[-1]
                ext_map = {b"doc": 2,
                           b"docx":2,
                           b"zip": 3,
                           b"7z": 3,
                           b"exe": 4,
                           b"com": 4,
                           b"bat": 4,
                           b"cmd": 4,
                           }
    
                if extension in ext_map:
                    node_type = ext_map[extension]
                else:
                    node_type = 1
            
            nodes_list.append((file, node_type, path_id ))
            if len(file) > max_entry_length:
                max_entry_length = len(file)
        path_id += 1
        if path_id % 1000 ==0:
            label.set(f"{len(nodes_list)} objects scanned...")
            
    # Print the length of files
    label.set(f"{len(nodes_list)} objects found. Creating database...")

    # Set the compression filters for the file
    filters = tb.Filters(complevel=5, complib='blosc:zstd', shuffle=True)
    
    
    # Create the file and create the tables
    with tb.open_file(file_name, 'w', filters=filters) as f:
        
        # Create the paths table
        paths_desc = {
            'path': tb.StringCol(itemsize=max_path_length)
        }
        paths_table = f.create_table('/', 'paths', paths_desc, expectedrows=len(paths_list))
        
        # Create the entries table
        entries_desc = {
            'partial_entry': tb.StringCol(itemsize=max_entry_length, pos=0),
        }
        # entries_table = f.create_table('/', 'entries', entries_desc, expectedrows=10*len(nodes_list))
    
    
        # Create the index table
        index_desc = {
            'entry_id': tb.Int64Col(pos=0),
            'file_id': tb.Int64Col(pos=1),
            'type': tb.UInt8Col(pos=2)
        }
        
        # Create the nodes table
        nodes_desc = {
            'entry': tb.StringCol(itemsize=max_entry_length, pos=0),
            'type': tb.UInt8Col(pos=1),
            'path_id': tb.Int64Col(pos=2)
        }
        nodes_table = f.create_table('/', 'nodes', nodes_desc, expectedrows=len(nodes_list))
        # insert paths
        paths_table.append(paths_list)
        # insert nodes
        nodes_table.append(nodes_list)
        # insert entries

        # The bitmap provides unicity, order and speed
        expanded_dict = defaultdict(BitMap)

        prev_progress = 0
        len(nodes_list)
        for idx, node in enumerate(nodes_list):
            progress = (idx*100)//len(nodes_list)
            if progress >= prev_progress + 5:
                prev_progress = progress
                label.set(f"Creating index... {progress}%")
            node = unidecode(node[0].decode("utf8").lower())
            expanded_nodes = []
            split_node = node.split()
            for snode in split_node:
                expanded_nodes.extend( [snode[i:].encode("utf8") for i in range(len(snode))])

            for expanded_node in expanded_nodes:
                expanded_dict[expanded_node].add(idx)
        
        # Insert in entries and index
        n =len(nodes_list)
        entries_table = f.create_table('/', "entries", entries_desc, expectedrows=n)
        index_table = f.create_table('/', "index", index_desc, expectedrows=n*3)
    

        # Extract unique elements from the first position of the tuples while keeping them sorted
        prev_progress = 0
        index_row = index_table.row
        entries_row = entries_table.row
        
        
        prev_match_length = 0
        prev_expanded_node = ""
        for idx_unique_nodes, expanded_node in enumerate(sorted(expanded_dict)):
           
            if idx_unique_nodes == 0:
                 prev_expanded_node = expanded_node
            else:
                match_length = first_different_byte(expanded_node, prev_expanded_node)
                if match_length<= prev_match_length:
                    entries_row["partial_entry"] = prev_expanded_node[:prev_match_length+1]
                else:
                    entries_row["partial_entry"] = prev_expanded_node
                entries_row.append()
                prev_match_length = match_length
                prev_expanded_node =expanded_node
            
            progress = (idx_unique_nodes*100)//len(expanded_dict)
            if progress >= prev_progress + 5:
                prev_progress = progress
                label.set(f"Inserting index... {progress}%")
            
            for idx in expanded_dict[expanded_node]:
                index_row["entry_id"] = idx_unique_nodes 
                index_row["file_id"] = idx
                index_row["type"] = nodes_list[idx][1]
                index_row.append()
        
        # last node
        entries_row["partial_entry"] = expanded_node
        entries_row.append()     
    
        f.flush()
        label.set("Finished")


if __name__ == "__main__":
    class Label():
        def set(self, text):
            print(text)

    label = Label()
    create_index("0.h5", "D:\\", label)