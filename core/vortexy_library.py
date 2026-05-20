import os


def build_library_index(library_root):
    index = {}
    if not library_root or not os.path.exists(library_root):
        return index
    for root, dirs, files in os.walk(library_root):
        for f in files:
            index[f.lower()] = os.path.join(root, f)
            no_ext = os.path.splitext(f)[0].lower()
            if no_ext not in index:
                index[no_ext] = os.path.join(root, f)
    return index


def find_pdf_in_library(original_name, lib_index):
    if not original_name or not lib_index:
        return None
    key = original_name.lower()
    if key in lib_index:
        return lib_index[key]
    no_ext = os.path.splitext(key)[0]
    return lib_index.get(no_ext)
