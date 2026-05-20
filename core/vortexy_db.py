try:
    import psycopg2
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False


def load_author_genre_map(cfg):
    db_cfg = cfg.get("db_config")
    if not db_cfg or not HAS_PSYCOPG:
        return {}
    try:
        conn = psycopg2.connect(
            host=db_cfg["host"], port=db_cfg["port"],
            user=db_cfg["user"], password=db_cfg["password"],
            dbname=db_cfg["dbname"]
        )
        cur = conn.cursor()
        cur.execute("SELECT author_name, subfolder FROM author_genre_map")
        result = {row[0]: row[1] for row in cur.fetchall()}
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print(f"  [db] Could not load author_genre_map: {e}")
        return {}
