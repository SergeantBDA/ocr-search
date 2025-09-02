from typing import Any, Dict
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings


def search_documents(session: Session, query: str, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
    """
    Ищет документы по PostgreSQL full-text (search_vector) + pg_trgm.
    Возвращает dict: {"total": int, "items": [{"id":..., "filename":..., "snippet":...}, ...]}
    """
    q = (query or "").strip()
    if not q:
        # Пустой запрос — вернём последние документы и общее количество
        total = session.execute(text("SELECT count(*) FROM documents")).scalar_one()
        rows = session.execute(
            text(
                "SELECT id, filename, path_origin, left(coalesce(content,''), 800) AS snippet "
                "FROM documents ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        ).mappings().all()
        items = [{"id": r["id"], 
                  "filename": r["filename"], 
                  "link"    :f'http://{settings.httpfs}/{r["path_origin"].replace("\\", "/")}',
                  "snippet": (r["snippet"] or "")} for r in rows]
        return {"total": int(total), "items": items}

    # Непустой запрос — комбинируем full-text и триграммы
    params = {"q": q, "limit": limit, "offset": offset}
    tsq = "plainto_tsquery('simple', :q)"

    where_sql = f"({{tsq}} @@ {tsq}) OR (content ILIKE '%' || :q || '%') OR (similarity(content, :q) > 0.2)".replace("{tsq}", "search_vector")
    # total count
    count_sql = f"SELECT count(*) FROM documents WHERE {where_sql}"
    total = session.execute(text(count_sql), params).scalar_one()

    # выборка с сниппетом и сортировкой по лучшему рангу (ts_rank_cd vs similarity)
    select_sql = f"""
    SELECT
      id,
      filename,
      path_origin,
      ts_headline('simple', content, {tsq}, 'MaxFragments=3, MinWords=3, ShortWord=3') AS snippet,
      ts_rank_cd(search_vector, {tsq}) AS rank,
      similarity(content, :q) AS sim
    FROM documents
    WHERE {where_sql}
    ORDER BY GREATEST(COALESCE(ts_rank_cd(search_vector, {tsq}), 0), COALESCE(similarity(content, :q), 0)) DESC
    LIMIT :limit OFFSET :offset
    """

    rows = session.execute(text(select_sql), params).mappings().all()
    items = []
    for r in rows:
        snippet = r.get("snippet") or ""
        items.append({"id"      : r["id"], 
                      "filename": r["filename"], 
                      "link"    :f'http://{settings.httpfs}/{r["path_origin"].replace("\\", "/")}', 
                      "snippet" : snippet})
    return {"total": int(total), "items": items}