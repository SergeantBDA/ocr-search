def ocr_file(file_path: str):
    """
    PDF:
      - если на странице есть текст → берём fitz-текст и копируем страницу «как есть» в результат;
      - если страницы-сканы → OCR только для них, вставляем OCR-страницы в выходной PDF.
    Изображения: полный OCR.
    Выход сохраняется в OUT_DIR с сохранением относительной структуры от IN_DIR.
    """
    try:
        ext = ext_lower(file_path)
        if ext not in SUPPORTED:
            move_to_err(file_path, f"Unsupported extension: {ext}")
            return

        out_txt_path, out_pdf_path = _make_out_paths(file_path)

        logger.info(f"OCR PDF (hybrid): {file_path}")

        # 1) Определяем страницы с текстом и собираем текстовый слой
        with fitz.open(file_path) as src:
            page_count = src.page_count
            logger.info(f"PDF pages: {page_count}")

            text_per_page: List[Optional[str]] = [None] * page_count
            is_scan_page: List[bool] = [False] * page_count

            for n in range(page_count):
                p = src.load_page(n)
                if page_has_text(p):
                    text_per_page[n] = extract_text_from_page(p)
                    is_scan_page[n] = False
                else:
                    is_scan_page[n] = True  # позже сделаем OCR

        # 2) OCR только скан-страниц (параллельно)
        ocr_results: dict[int, Tuple[str, bytes]] = {}
        scan_indices = [i for i, flag in enumerate(is_scan_page) if flag]
        if scan_indices:
            logger.info(f"Scanning pages via OCR: {len(scan_indices)}")
            def run_ocr(n: int) -> Tuple[int, str, bytes]:
                img = render_page_to_image(file_path, n, dpi=OCR_DPI)
                txt, pdf_bytes = ocr_image_to_text_and_pdf(img)
                return n, txt, pdf_bytes

            with concurrent.futures.ThreadPoolExecutor(max_workers=OCR_THREADS) as pool:
                futures = [pool.submit(run_ocr, n) for n in scan_indices]
                for fut in concurrent.futures.as_completed(futures):
                    n, txt, pdf_bytes = fut.result()
                    ocr_results[n] = (txt, pdf_bytes)
                    text_per_page[n] = preprocess_text_layer(txt)

        # 3) TXT
        if OUTPUT_TXT:
            os.makedirs(os.path.dirname(out_txt_path), exist_ok=True)
            with open(out_txt_path, "w", encoding="utf-8") as f:
                for n, page_text in enumerate(text_per_page):
                    if n > 0:
                        f.write("\n\n")
                    f.write(page_text or "")

        # 4) PDF
        if OUTPUT_PDF:
            os.makedirs(os.path.dirname(out_pdf_path), exist_ok=True)
            with fitz.open(file_path) as src, fitz.open() as outdoc:
                for n in range(src.page_count):
                    if not is_scan_page[n]:
                        # Копируем исходную страницу (текстовый слой сохранится)
                        outdoc.insert_pdf(src, from_page=n, to_page=n)
                    else:
                        # Вставляем одностраничный OCR-PDF
                        txt_pdf = ocr_results[n][1]
                        with fitz.open(stream=txt_pdf, filetype="pdf") as ocr_page_doc:
                            outdoc.insert_pdf(ocr_page_doc)
                outdoc.save(out_pdf_path)

        logger.info(f"OCR done: {file_path} -> {os.path.dirname(out_txt_path)}")

    except Exception as e:
        logger.exception(f"OCR failed: {file_path}: {e}")
        move_to_err(file_path, str(e))
