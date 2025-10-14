# --- помести эти импорты в верх файла, если их нет ---
from __future__ import annotations
import logging
import io, os, re, tempfile
from pathlib import Path
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from .base import BytesExtractor

try:
    import extract_msg  # для .msg
except Exception:
    extract_msg = None

try:
    from msg_parser import MsOxMessage  # альтернативная либра для .msg
except Exception:
    MsOxMessage = None

try:
    from bs4 import BeautifulSoup  # красивее чистит HTML
except Exception:
    BeautifulSoup = None

# ------------------------- logging --------------------------------------
from app.logger_worker import worker_log as app_logger

def _html_to_text(html: str) -> str:
    if not html:
        return ""
    if BeautifulSoup:
        return BeautifulSoup(html, "html.parser").get_text(separator="\n")
    # простой фоллбек
    return re.sub(r"<[^>]+>", "", html)


class EMLMSGExtractor(BytesExtractor):
    """
    Универсальный парсер email-сообщений:
    - .eml (RFC 822) через email.parser (bytes/файл)
    - .msg (Outlook) через extract_msg или msg_parser (файл/bytes)
    """
    def extract_text(self) -> str:
        name = (self.payload.filename or (Path(self.payload.path).name if self.payload.path else "")).lower()
        mime = (self.payload.mime or "").lower()
        is_msg = name.endswith(".msg") or mime in {
            "application/vnd.ms-outlook", "application/x-msg",
            "application/octet-stream"  # часто так присылается .msg
        }
        if is_msg:
            return self._extract_msg()
        return self._extract_eml()

    # ---------- EML ----------
    def _extract_eml(self) -> str:
        try:
            parser = BytesParser(policy=policy.default)
            if self.payload.path:
                with open(self.payload.path, "rb") as fp:
                    msg = parser.parse(fp)
            else:
                msg = parser.parsebytes(self.payload.content or b"")
        except Exception as e:
            app_logger.exception("Ошибка парсинга EML: %s", e)
            return ""

        def _safe(v): return "" if v is None else str(v)

        hdr_from  = _safe(msg.get("from"))
        hdr_to    = _safe(msg.get("to"))
        hdr_cc    = _safe(msg.get("cc"))
        hdr_subj  = _safe(msg.get("subject"))
        hdr_date  = _safe(msg.get("date"))

        # тело
        text_part, html_part = "", ""
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            dispo = part.get_content_disposition()  # None / inline / attachment
            if dispo == "attachment":
                continue
            if ctype == "text/plain" and not text_part:
                try:
                    text_part = part.get_content()
                except Exception:
                    pass
            elif ctype == "text/html" and not html_part:
                try:
                    html_part = part.get_content()
                except Exception:
                    pass

        body = text_part or _html_to_text(html_part)

        # вложения
        try:
            atts = [att.get_filename() or "attachment" for att in msg.iter_attachments()]
        except Exception:
            atts = []

        lines = [
            f"Тема: {hdr_subj}",
            f"От  : {hdr_from}",
            f"Кому: {hdr_to}",
            f"Копия: {hdr_cc}",
            f"Дата: {hdr_date}",
        ]
        if body:
            lines.append("Тело письма:\n" + body)
        if atts:
            lines.append("Вложения:\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(atts)))
        return "\n".join(lines)

    # ---------- MSG ----------
    def _extract_msg(self) -> str:
        # 1) Пытаемся через extract_msg
        if extract_msg is not None:
            try:
                if self.payload.path:
                    m = extract_msg.Message(self.payload.path)
                else:
                    # extract_msg работает по пути — сделаем временный файл
                    with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as tmp:
                        tmp.write(self.payload.content or b"")
                        tmp_path = tmp.name
                    try:
                        m = extract_msg.Message(tmp_path)
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass

                subj  = m.subject or ""
                from_ = m.sender or m.sender_email or ""
                to    = ", ".join([r.email or r.name for r in (m.recipients or [])]) if hasattr(m, "recipients") else (m.to or "")
                cc    = m.cc or ""
                date  = str(m.date) if getattr(m, "date", None) else ""

                body_text = getattr(m, "body", "") or ""
                body_html = getattr(m, "htmlBody", "") or ""
                body = body_text or _html_to_text(body_html)

                # вложения
                atts = []
                try:
                    for a in (m.attachments or []):
                        # extract_msg.attachments — объекты с полями .filename, .save()
                        atts.append(a.longFilename or a.shortFilename or a.filename or "attachment")
                except Exception:
                    pass

                lines = [
                    f"Тема: {subj}",
                    f"От  : {from_}",
                    f"Кому: {to}",
                    f"Копия: {cc}",
                    f"Дата: {date}",
                ]
                if body:
                    lines.append("Тело письма:\n" + body)
                if atts:
                    lines.append("Вложения:\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(atts)))
                return "\n".join(lines).strip()
            except Exception as e:
                app_logger.warning("extract_msg не справился: %s. Пытаюсь через msg_parser…", e)

        # 2) Фоллбек: msg_parser (MsOxMessage)
        if MsOxMessage is not None:
            try:
                if self.payload.path:
                    msg = MsOxMessage(self.payload.path)
                else:
                    bio = io.BytesIO(self.payload.content or b"")
                    msg = MsOxMessage(bio)

                props = msg.get_properties() if hasattr(msg, "get_properties") else msg.getProperties()
                # ключи сильно зависят от версии lib — берём самые частые
                subj  = props.get("subject", "") or props.get("Subject", "")
                from_ = props.get("sender_email", "") or props.get("from", "") or props.get("SenderEmailAddress", "")
                to    = props.get("to", "") or props.get("DisplayTo", "")
                cc    = props.get("cc", "") or props.get("DisplayCc", "")
                date  = props.get("date", "") or props.get("message_delivery_time", "") or props.get("CreationTime", "")

                body_text = props.get("body", "") or props.get("Body", "")
                body_html = props.get("html", "") or props.get("Html", "")
                body = body_text or _html_to_text(body_html)

                atts = []
                for a in (props.get("attachments") or []):
                    if isinstance(a, dict):
                        atts.append(a.get("filename") or a.get("name") or "attachment")
                    else:
                        atts.append(str(a))

                lines = [
                    f"Тема: {subj}",
                    f"От  : {from_}",
                    f"Кому: {to}",
                    f"Копия: {cc}",
                    f"Дата: {date}",
                ]
                if body:
                    lines.append("Тело письма:\n" + body)
                if atts:
                    lines.append("Вложения:\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(atts)))
                return "\n".join(lines).strip()
            except Exception as e:
                app_logger.exception("Ошибка парсинга MSG через msg_parser: %s", e)

        app_logger.error("Ни extract_msg, ни msg_parser недоступны — не могу разобрать .msg")
        return "Файл формата .msg: требуется установить пакет 'extract_msg' или 'msg-parser'."
