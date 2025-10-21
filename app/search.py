from typing import Any, Dict
from sqlalchemy.orm import Session
from app.config import settings
from sqlalchemy import text, bindparam, String, DateTime, Integer

import logging
from app.logger import logger as app_logger, attach_to_logger_names
attach_to_logger_names(["app.search"])

def search_documents(session: Session, 
                     q,
                     ocr_user,
                     ocr_from,
                     ocr_to,
                     limit: int = 25, 
                     offset: int = 0) -> Dict[str, Any]:
#def search_documents(session: Session, query: str) -> Dict[str, Any]:
    """
    Ищет документы по PostgreSQL full-text (search_vector) + pg_trgm.
    Возвращает dict: {"total": int, "items": [{"id":..., "filename":..., "snippet":...}, ...]}
    """    
    q= (q or "").strip()
    
    if not (q or ocr_user or ocr_from or ocr_to) :
        # Пустой запрос — вернём последние 10 документов и общее количество
        total = session.execute(text("SELECT count(*) FROM documents")).scalar_one()
        rows  = session.execute(
            text("SELECT null as id, '' as filename, '' as path_origin, 'Пустой запрос' AS snippet"
                #"SELECT id, filename, path_origin, left(coalesce(content,''), 800) AS snippet "
                #"FROM documents ORDER BY created_at DESC LIMIT 10"
            ),
            {"limit": limit, "offset": offset},
        ).mappings().all()
        items = [{"id"             :r["id"], 
                  "filename"       :r["filename"], 
                  "link"           :f'http://{settings.httpfs}/{r["path_origin"].replace("\\", "/")}',
                  "snippet"        :(r["snippet"] or ""),
                  "snippet_is_html":False} for r in rows]
        return {"total": int(total), "items": items}   

    ocr_from = (ocr_from or "2000-01-01T00:00")
    ocr_to   = (ocr_to   or "2100-01-01T00:00")

    # Непустой запрос — комбинируем full-text и триграммы
    params = {"q": q,
              "ocr_user":ocr_user or None,
              "ocr_from":ocr_from,
              "ocr_to"  :ocr_to}

    #tsq = "plainto_tsquery('simple', :q)"
    tsq = "websearch_to_tsquery(:q)"
    where_sql = f"""((search_vector @@ {tsq})  
                     OR (filename ILIKE '%' || :q || '%') 
                     OR (content  ILIKE '%' || :q || '%') 
                     OR (similarity(content, :q) > 0.2)) 
                     AND (:ocr_from IS NULL OR created_at >= :ocr_from)
                     AND (:ocr_to   IS NULL OR created_at <= :ocr_to  )
                     AND (:ocr_user IS NULL OR email ILIKE '%' || :ocr_user || '%')"""    

    count_sql = text( f"""SELECT count(*) FROM documents 
                          WHERE {where_sql}
                          """).bindparams(  
                                    bindparam("q", type_=String),
                                    bindparam("ocr_user", type_=String),
                                    bindparam("ocr_from", type_=DateTime),
                                    bindparam("ocr_to", type_=DateTime),
                                )

    total = session.execute(count_sql, params).scalar_one()
    
    # выборка с сниппетом и сортировкой по лучшему рангу (ts_rank_cd vs similarity)
    select_sql = text(f"""
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
    """).bindparams(  
                bindparam("q", type_=String),
                bindparam("ocr_user", type_=String),
                bindparam("ocr_from", type_=DateTime),
                bindparam("ocr_to", type_=DateTime),
        )

    app_logger.debug("Search SQL: %s", select_sql)
    rows = session.execute(select_sql, params).mappings().all()
    items = []
    for r in rows:
        snippet = r.get("snippet") or ""
        items.append({"id"             :r["id"], 
                      "filename"       :r["filename"], 
                      "link"           :f'http://{settings.httpfs}/{r["path_origin"].replace("\\", "/")}', 
                      "snippet"        :snippet,
                      "snippet_is_html":True})
    return {"total": int(total), "items": items}