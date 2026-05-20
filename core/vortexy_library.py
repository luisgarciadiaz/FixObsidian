import os
import pickle
import time

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
INDEX_CACHE = os.path.join(CACHE_DIR, "library_index.pkl")
CACHE_TTL = 86400  # 24 hours


def build_library_index(library_root):
    index = {}
    if not library_root or not os.path.exists(library_root):
        return index

    if os.path.exists(INDEX_CACHE):
        try:
            mtime = os.path.getmtime(INDEX_CACHE)
            if time.time() - mtime < CACHE_TTL:
                with open(INDEX_CACHE, "rb") as f:
                    cached = pickle.load(f)
                if cached.get("_root") == library_root:
                    return cached.get("_index", {})
        except (pickle.UnpicklingError, KeyError, EOFError):
            pass

    print("  (walking library tree — this may take a moment...)")
    for root, dirs, files in os.walk(library_root):
        for f in files:
            index[f.lower()] = os.path.join(root, f)
            no_ext = os.path.splitext(f)[0].lower()
            if no_ext not in index:
                index[no_ext] = os.path.join(root, f)

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(INDEX_CACHE, "wb") as f:
        pickle.dump({"_root": library_root, "_index": index}, f, protocol=pickle.HIGHEST_PROTOCOL)
    return index


def find_pdf_in_library(original_name, lib_index):
    if not original_name or not lib_index:
        return None
    key = original_name.lower()
    if key in lib_index:
        return lib_index[key]
    no_ext = os.path.splitext(key)[0]
    return lib_index.get(no_ext)
