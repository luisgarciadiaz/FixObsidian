import os
import re

from core.vortexy_obsidian import normalize_author_name
from core.vortexy_parsers import extract_file_uri

BAD_PREFIXES = {"an", "el", "los", "la", "mi", "no", "lg", "m", "dune", "dragon",
                "stephen", "charles", "patricia", "historia", "platon", "homero",
                "isabel", "gabriel", "mao", "the", "de", "las", "del"}
NUM_PREFIX_RE = re.compile(r"^\d{1,2}\s*[- ]\s*")
CHAPTER_PREFIX_RE = re.compile(r"^(\d{2}[A-Z]?)\s*-\s+(.+)$")
EXTENSIONS_RE = re.compile(r'\.(pdf|epub|mobi|azw3|djvu|mp3|mp4|wma|wmv|avi|mkv|srt|vtt|zip|rar|txt)$', re.IGNORECASE)
BRACKET_INFO_RE = re.compile(r'\[([^\]]+)\]')
YEAR_RE = re.compile(r'\b(1[89]\d{2}|20[0-2]\d)\b')
ISBN_PREFIX_RE = re.compile(r'^[\d\-]{10,17}\s+')
CURLY_HASH_RE = re.compile(r'\{[^}]*\}')


def _norm_compare(s):
    return re.sub(r'[.\s]+', '', s).lower()


def strip_author_prefix(text, author):
    if not text or not author or author in ("Unknown Author", "Unknown"):
        return text
    norm_author = _norm_compare(author)
    for sep in [' - ', ' \u2013 ', ' \u2014 ', ' _ ']:
        if sep in text:
            prefix, rest = text.split(sep, 1)
            if _norm_compare(prefix) == norm_author:
                return rest.strip()
    norm_text = _norm_compare(text)
    if norm_text.startswith(norm_author):
        pos = 0
        ai = 0
        while ai < len(norm_author) and pos < len(text):
            if _norm_compare(text[pos]) == norm_author[ai]:
                ai += 1
            pos += 1
        rest = text[pos:].strip().lstrip('-\u2013\u2014_ ').strip()
        if rest:
            return rest
    return text


def parse_author_title_from_filename(filename):
    name_no_ext = os.path.splitext(filename)[0]
    name_no_ext = NUM_PREFIX_RE.sub("", name_no_ext)
    for sep in [" - ", " -", "- "]:
        if sep in name_no_ext:
            segments = [s.strip() for s in name_no_ext.split(sep) if s.strip()]
            if len(segments) >= 2:
                first = segments[0]
                if first.isdigit() or (len(first) <= 2 and first.isalnum() and first[0].isdigit()):
                    continue
                return first, " - ".join(segments[1:])
    return None, name_no_ext


def strip_bad_prefix(raw):
    raw = NUM_PREFIX_RE.sub("", raw)
    for sep in [" - ", " _ ", " - "]:
        if sep in raw:
            first, rest = raw.split(sep, 1)
            if first.strip().lower() in BAD_PREFIXES:
                return rest.strip(), first.strip()
    m = CHAPTER_PREFIX_RE.match(raw)
    if m:
        return m.group(2).strip(), m.group(1)
    return raw, None


def extract_bracket_info(raw):
    m = BRACKET_INFO_RE.search(raw)
    if not m:
        return raw, None, None
    bracket_content = m.group(1).strip()
    year_match = YEAR_RE.search(bracket_content)
    year = year_match.group(0) if year_match else None
    if year:
        author = YEAR_RE.sub('', bracket_content).strip().strip(',').strip()
    else:
        author = bracket_content
    cleaned = BRACKET_INFO_RE.sub('', raw, count=1).strip()
    return cleaned, author if author else None, year


def strip_isbn_prefix(raw):
    return ISBN_PREFIX_RE.sub('', raw).strip()


def strip_curly_hash(raw):
    return CURLY_HASH_RE.sub('', raw).strip()


def resolve_author_title(filepath, fm, body, existing_author, existing_title, lib_index, original_name):
    author = "Unknown Author"
    title = ""
    chapter = ""
    year = None
    pdf_path = None

    file_uri = extract_file_uri(body)
    if file_uri and os.path.exists(file_uri):
        pdf_path = file_uri
    elif original_name and lib_index:
        from core.vortexy_library import find_pdf_in_library
        found = find_pdf_in_library(original_name, lib_index)
        if found:
            pdf_path = found
            file_uri = found

    if pdf_path:
        pdf_fname = os.path.basename(pdf_path)
        f_author, f_title = parse_author_title_from_filename(pdf_fname)
        if f_author:
            author = normalize_author_name(f_author)
            title = f_title
        else:
            title = os.path.splitext(pdf_fname)[0]

    if author == "Unknown Author" and existing_author:
        ex = existing_author.strip().lower()
        if ex and ex not in ("unknown", "desconocido", "") and ex not in BAD_PREFIXES:
            author = normalize_author_name(existing_author)

    if author == "Unknown Author":
        note_fname = os.path.basename(filepath)
        clean_raw, prefix = strip_bad_prefix(note_fname)
        if prefix and prefix.lower() not in BAD_PREFIXES:
            chapter = prefix
        clean_raw = NUM_PREFIX_RE.sub("", clean_raw)
        fn_no_ext = clean_raw.replace(".md", "")

        bracket_clean, bracket_author, bracket_year = extract_bracket_info(fn_no_ext)
        if bracket_author and bracket_author.lower() not in BAD_PREFIXES:
            author = normalize_author_name(bracket_author)
            year = bracket_year
            title_from_bracket = strip_isbn_prefix(bracket_clean)
            title_from_bracket = strip_curly_hash(title_from_bracket)
            if not title and title_from_bracket:
                title = title_from_bracket
        else:
            f_author, f_title = parse_author_title_from_filename(fn_no_ext)
            if f_author and f_author.lower() not in BAD_PREFIXES:
                author = normalize_author_name(f_author)
                if not title:
                    title = f_title
            elif not chapter:
                clean_raw2, prefix2 = strip_bad_prefix(note_fname.replace(".md", ""))
                if prefix2:
                    chapter = prefix2

    if not title:
        if existing_title:
            title = existing_title
        else:
            note_fname = os.path.basename(filepath)
            clean_raw, _ = strip_bad_prefix(note_fname.replace(".md", ""))
            title = clean_raw

    title = strip_isbn_prefix(title)
    title = strip_curly_hash(title)
    title = EXTENSIONS_RE.sub('', title).strip()
    title = re.sub(r'^[-\u2013\u2014_.,;:\s]+', '', title).strip()
    cleaned = strip_author_prefix(title, author)
    if cleaned != title:
        title = cleaned
    title = re.sub(r'^[-\u2013\u2014_.,;:\s]+', '', title).strip()
    return author, title, file_uri, chapter, year
