"""Repositorio de Catálogo Híbrido (MySQL -> MongoDB, Parte E).

REGLA DE ORO: El 100 % de las consultas SQL emplean marcadores de parámetros (%s).
Ninguna variable se concatena en cadenas SQL.
"""
from app.mongo import get_films_collection


def _parse_special_features(raw_val):
    """Convierte el tipo SET de MySQL en una lista limpia de strings."""
    if not raw_val:
        return []
    if isinstance(raw_val, (set, list, tuple)):
        return sorted(str(x).strip() for x in raw_val if str(x).strip())
    return [s.strip() for s in str(raw_val).split(",") if s.strip()]


def fetch_film_from_mysql(cur, film_id: int):
    """Extrae una película específica desde MySQL con su idioma, categorías y actores."""
    cur.execute(
        """SELECT f.film_id, f.title, f.description, f.release_year,
                  l.name AS language_name, f.rental_duration, f.rental_rate,
                  f.length, f.replacement_cost, f.rating, f.special_features
           FROM film f
           INNER JOIN language l ON f.language_id = l.language_id
           WHERE f.film_id = %s;""",
        (film_id,),
    )
    film_row = cur.fetchone()
    if not film_row:
        return None

    (
        f_id,
        title,
        description,
        release_year,
        lang_name,
        rental_duration,
        rental_rate,
        length,
        replacement_cost,
        rating,
        special_features,
    ) = film_row

    cur.execute(
        """SELECT c.name
           FROM film_category fc
           INNER JOIN category c ON fc.category_id = c.category_id
           WHERE fc.film_id = %s
           ORDER BY c.name;""",
        (film_id,),
    )
    categories = [r[0].strip() for r in cur.fetchall()]

    cur.execute(
        """SELECT a.actor_id, a.first_name, a.last_name
           FROM film_actor fa
           INNER JOIN actor a ON fa.actor_id = a.actor_id
           WHERE fa.film_id = %s
           ORDER BY a.actor_id;""",
        (film_id,),
    )
    actors = [
        {"actor_id": int(r[0]), "name": f"{r[1].strip()} {r[2].strip()}"}
        for r in cur.fetchall()
    ]

    return {
        "_id": int(f_id),
        "title": title,
        "description": description,
        "release_year": int(release_year) if release_year is not None else None,
        "language": lang_name.strip() if lang_name else None,
        "rental_duration": int(rental_duration),
        "rental_rate": float(rental_rate),
        "length": int(length) if length is not None else None,
        "replacement_cost": float(replacement_cost),
        "rating": str(rating) if rating else None,
        "categories": categories,
        "actors": actors,
        "special_features": _parse_special_features(special_features),
    }


def fetch_all_films_from_mysql(cur):
    """Extrae todas las películas de MySQL y construye sus documentos desnormalizados en memoria."""
    cur.execute(
        """SELECT f.film_id, f.title, f.description, f.release_year,
                  l.name AS language_name, f.rental_duration, f.rental_rate,
                  f.length, f.replacement_cost, f.rating, f.special_features
           FROM film f
           INNER JOIN language l ON f.language_id = l.language_id
           ORDER BY f.film_id;"""
    )
    film_rows = cur.fetchall()

    cur.execute(
        """SELECT fc.film_id, c.name
           FROM film_category fc
           INNER JOIN category c ON fc.category_id = c.category_id
           ORDER BY fc.film_id, c.name;"""
    )
    cats_by_film = {}
    for f_id, c_name in cur.fetchall():
        cats_by_film.setdefault(int(f_id), []).append(c_name.strip())

    cur.execute(
        """SELECT fa.film_id, a.actor_id, a.first_name, a.last_name
           FROM film_actor fa
           INNER JOIN actor a ON fa.actor_id = a.actor_id
           ORDER BY fa.film_id, a.actor_id;"""
    )
    actors_by_film = {}
    for f_id, a_id, first_name, last_name in cur.fetchall():
        actors_by_film.setdefault(int(f_id), []).append(
            {"actor_id": int(a_id), "name": f"{first_name.strip()} {last_name.strip()}"}
        )

    docs = []
    for row in film_rows:
        (
            f_id,
            title,
            description,
            release_year,
            lang_name,
            rental_duration,
            rental_rate,
            length,
            replacement_cost,
            rating,
            special_features,
        ) = row
        f_id = int(f_id)
        docs.append(
            {
                "_id": f_id,
                "title": title,
                "description": description,
                "release_year": int(release_year) if release_year is not None else None,
                "language": lang_name.strip() if lang_name else None,
                "rental_duration": int(rental_duration),
                "rental_rate": float(rental_rate),
                "length": int(length) if length is not None else None,
                "replacement_cost": float(replacement_cost),
                "rating": str(rating) if rating else None,
                "categories": cats_by_film.get(f_id, []),
                "actors": actors_by_film.get(f_id, []),
                "special_features": _parse_special_features(special_features),
            }
        )
    return docs


def upsert_film_in_mongo(doc: dict):
    """Inserta o reemplaza un documento de película en la colección MongoDB."""
    coll = get_films_collection()
    coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)
    return doc


def find_films_in_mongo(category=None, actor=None, max_rate=None, page=1, page_size=20):
    """Consulta paginada sobre la colección `films` en MongoDB con filtros opcionales."""
    coll = get_films_collection()
    query = {}

    if category:
        query["categories"] = category
    if actor:
        query["actors.name"] = actor.upper()
    if max_rate is not None:
        query["rental_rate"] = {"$lte": float(max_rate)}

    skip = (page - 1) * page_size
    total = coll.count_documents(query)
    cursor = coll.find(query).sort("_id", 1).skip(skip).limit(page_size)
    items = list(cursor)

    return total, items


def get_film_from_mongo(film_id: int):
    """Obtiene un documento de película por su _id desde MongoDB."""
    coll = get_films_collection()
    return coll.find_one({"_id": int(film_id)})

