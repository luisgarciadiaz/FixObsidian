import json
import os
import re
import time
import unicodedata
import threading
import urllib.request
import urllib.parse
import urllib.error

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DEFAULT_CACHE = os.path.join(CACHE_DIR, "metadata_cache.json")

def _norm_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s.lower().strip()) if not unicodedata.combining(c))


class MetadataEnricher:
    def __init__(self, subfolder_map, dry_run=False, cache_path=None):
        self.subfolder_map = subfolder_map
        self.dry_run = dry_run
        self.cache_path = cache_path or DEFAULT_CACHE
        self._cache = {}
        self._dirty = 0
        self._lock = threading.Lock()
        self._load_cache()

    def _load_cache(self):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_cache(self):
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2, ensure_ascii=False)

    def flush(self):
        with self._lock:
            if self._dirty > 0:
                self._save_cache()
                self._dirty = 0

    def clear_cache(self):
        with self._lock:
            self._cache = {}
            self._save_cache()

    def _cache_key(self, isbn, title, author, year=None):
        clean = re.sub(r'[^0-9Xx]', '', isbn or "") if isbn else ""
        if clean:
            return f"isbn:{clean}"
        key = f"title:{_norm_accents(title)}|{_norm_accents(author)}"
        if year:
            key += f"|{year}"
        return key

    def _fetch(self, url, retries=2):
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "FixObsidian/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception:
                if attempt < retries:
                    time.sleep(1)
        return None

    def _isbn_api(self, clean_isbn):
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&format=json&jscmd=data"
        data = self._fetch(url)
        if not data:
            return None
        book = data.get(f"ISBN:{clean_isbn}")
        if not book:
            return None
        r = {}
        r["title"] = book.get("title", "")
        r["publish_date"] = book.get("publish_date", "")
        pubs = book.get("publishers", [])
        r["publisher"] = pubs[0].get("name", "") if pubs else ""
        r["subjects"] = [s.get("name", "") for s in book.get("subjects", [])]
        works = book.get("works", [])
        r["work_key"] = works[0].get("key", "") if works else ""
        cover = book.get("cover", {})
        r["cover_url"] = cover.get("medium", "") if cover else self._cover_url_from_cover_i(book.get("cover_i"))
        return r

    def _cover_url_from_cover_i(self, cover_i):
        if cover_i:
            return f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
        return ""

    def _search(self, isbn="", title="", author=""):
        params = []
        if isbn:
            params.append(f"isbn={urllib.parse.quote(isbn)}")
        if title:
            params.append(f"title={urllib.parse.quote(title.strip())}")
        if author:
            params.append(f"author={urllib.parse.quote(author.strip())}")
        data = self._fetch(f"https://openlibrary.org/search.json?{'&'.join(params)}")
        if not data or not data.get("docs"):
            return None
        doc = data["docs"][0]
        r = {}
        r["title"] = doc.get("title", "")
        y = doc.get("first_publish_year")
        r["publish_date"] = str(y) if y else ""
        pubs = doc.get("publisher", [])
        r["publisher"] = ", ".join(pubs) if isinstance(pubs, list) else ""
        r["subjects"] = doc.get("subject", [])
        r["work_key"] = doc.get("key", "")
        isbns = doc.get("isbn", [])
        r["discovered_isbn"] = isbns[0] if isbns else ""
        r["cover_url"] = self._cover_url_from_cover_i(doc.get("cover_i"))
        return r

    def _work(self, work_key):
        if not work_key:
            return {}
        data = self._fetch(f"https://openlibrary.org{work_key}.json")
        if not data:
            return {}
        desc = data.get("description", "")
        if isinstance(desc, dict):
            desc = desc.get("value", "")
        covers = data.get("covers", [])
        cover_url = self._cover_url_from_cover_i(covers[0]) if covers else ""
        return {"synopsis": desc, "subjects": data.get("subjects", []), "cover_url": cover_url}

    def _map_subjects(self, subjects):
        if not subjects:
            return None
        best, best_len = None, 0
        for s in subjects:
            sl = s.lower().strip()
            for folder, keywords in self.subfolder_map.items():
                for kw in keywords:
                    if kw.lower() in sl and len(kw) > best_len:
                        best_len = len(kw)
                        best = folder
        return best

    def _is_garbage_request(self, isbn, title, author):
        clean_isbn = re.sub(r'[^0-9Xx]', '', isbn or "") if isbn else ""
        if clean_isbn and len(clean_isbn) < 10:
            clean_isbn = ""
        if clean_isbn:
            return False
        if not title or not title.strip():
            return True
        tstrip = title.strip()
        if len(tstrip) < 3:
            return True
        if re.match(r'^[\d\s\-\.]+$', tstrip):
            return True
        if author == "Unknown Author":
            return True
        return False

    def enrich(self, isbn, title, author, year=None):
        if self._is_garbage_request(isbn, title, author):
            return {}
        key = self._cache_key(isbn, title, author, year)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        if self.dry_run:
            return {}
        result = {}
        clean_isbn = re.sub(r'[^0-9Xx]', '', isbn or "") if isbn else ""
        book = None
        if clean_isbn:
            book = self._isbn_api(clean_isbn)
            if not book:
                book = self._search(isbn=clean_isbn)
        if not book and title and author:
            book = self._search(title=title, author=author)
        if not book:
            with self._lock:
                self._cache[key] = {}
                self._dirty += 1
                if self._dirty % 50 == 0:
                    self._save_cache()
            return {}
        subjects = book.get("subjects", [])
        wd = {}
        if book.get("work_key"):
            wd = self._work(book["work_key"])
            subjects = subjects + wd.get("subjects", [])
        result["publisher"] = book.get("publisher", "")
        result["publish_date"] = book.get("publish_date", "")
        result["synopsis"] = wd.get("synopsis", "")
        result["suggested_category"] = self._map_subjects(subjects) or ""
        result["discovered_isbn"] = book.get("discovered_isbn", "")
        result["cover_url"] = book.get("cover_url", "") or wd.get("cover_url", "")
        result["_ts"] = time.time()
        time.sleep(0.05)
        with self._lock:
            self._cache[key] = result
            self._dirty += 1
            if self._dirty % 50 == 0:
                self._save_cache()
        return result
