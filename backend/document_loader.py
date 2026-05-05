"""Load documents from PDF, DOCX, and TXT files."""

import logging
import re
from pathlib import Path

from PyPDF2 import PdfReader

logger = logging.getLogger("smartqa")


def load_pdf(file_path: str) -> list[dict]:
    """Load PDF with automatic fallback to OCR for scanned documents.

    1. Try PyPDF2 text extraction (fast, works for text-based PDFs)
    2. If result is mostly empty/garbage, fall back to PaddleOCR
    """
    reader = PdfReader(file_path)
    if reader.is_encrypted:
        raise ValueError("PDF 文件已加密，请先解密后再上传")

    # --- Attempt 1: PyPDF2 direct text extraction ---
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            pages.append({
                "content": text.strip(),
                "metadata": {"source": file_path, "page": i + 1}
            })

    # Check if extraction was successful (>30% pages have content)
    if pages and len(pages) >= len(reader.pages) * 0.3:
        logger.info(f"[PDF] 文本提取成功: {len(pages)}/{len(reader.pages)} 页")
        return pages

    # --- Attempt 2: OCR for scanned PDFs ---
    logger.info(f"[PDF] 文本提取不足，尝试 OCR 识别...")
    try:
        ocr_pages = _ocr_pdf(file_path)
        if ocr_pages:
            logger.info(f"[PDF] OCR 识别成功: {len(ocr_pages)} 页")
            return ocr_pages
    except ImportError:
        logger.warning("[PDF] PaddleOCR 未安装，无法识别扫描件")
    except Exception as e:
        logger.error(f"[PDF] OCR 识别失败: {e}")

    if pages:
        return pages

    raise ValueError("PDF 文件无法提取文本，请确认文件格式或安装 PaddleOCR")


def _ocr_pdf(file_path: str) -> list[dict]:
    """Use PaddleOCR to extract text from scanned PDF pages."""
    import fitz  # PyMuPDF
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    doc = fitz.open(file_path)
    pages = []

    for i in range(len(doc)):
        page = doc[i]
        # Render page to image (2x resolution for better OCR)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")

        # OCR recognize
        result = ocr.ocr(img_bytes, cls=True)

        if not result or not result[0]:
            continue

        # Extract text lines, sorted by vertical position
        lines = []
        for line in result[0]:
            text = line[1][0]  # recognized text
            y_pos = line[0][0][1]  # top-left y coordinate
            lines.append((y_pos, text))

        lines.sort(key=lambda x: x[0])
        page_text = "\n".join(t for _, t in lines)

        if page_text.strip():
            pages.append({
                "content": page_text.strip(),
                "metadata": {"source": file_path, "page": i + 1}
            })

    doc.close()
    return pages


def load_docx(file_path: str) -> list[dict]:
    """Load DOCX with complete text extraction using mammoth.

    mammoth handles text boxes, tables, headers, footers, drawings,
    and all embedded content that python-docx misses.
    """
    import mammoth

    with open(file_path, "rb") as f:
        result = mammoth.convert_to_html(f, include_embedded_style_map=True)

    html = result.value  # full HTML string
    messages = result.messages  # conversion warnings

    # Parse HTML to extract paragraph-level text
    paragraphs = _html_to_paragraphs(html)

    if not paragraphs:
        raise ValueError("DOCX 文件内容为空")

    output = []
    for i, text in enumerate(paragraphs):
        output.append({
            "content": text,
            "metadata": {"source": file_path, "paragraph": i + 1}
        })

    return output


def _html_to_paragraphs(html: str) -> list[str]:
    """Convert mammoth HTML output into clean paragraph list.

    Handles: <p>, <h1>-<h6>, <li>, <td>, <br>, <table>.
    """
    from lxml import etree

    # Wrap in root if needed
    html = html.strip()
    if not html.startswith("<"):
        html = f"<div>{html}</div>"
    else:
        html = f"<div>{html}</div>"

    # Remove XML declaration issues
    try:
        root = etree.HTML(html)
    except Exception:
        # Fallback: strip all tags
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return [text] if text else []

    paragraphs = []

    # Walk all block-level elements in document order
    for elem in root.iter():
        tag = elem.tag.lower() if isinstance(elem.tag, str) else ""

        if tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            text = _get_element_text(elem).strip()
            if text:
                paragraphs.append(text)
        elif tag in ("td", "th"):
            text = _get_element_text(elem).strip()
            if text:
                paragraphs.append(text)
        elif tag == "br":
            continue

    # If nothing was extracted, try raw text
    if not paragraphs:
        text = _get_element_text(root).strip()
        if text:
            # Split by double newline or single newline for paragraphs
            parts = re.split(r'\n{2,}|\n', text)
            paragraphs = [p.strip() for p in parts if p.strip()]

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in paragraphs:
        key = p[:100]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def _get_element_text(elem) -> str:
    """Get all text content from an element, including nested text, with spaces between inline elements."""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        tag = child.tag.lower() if isinstance(child.tag, str) else ""
        if tag == "br":
            parts.append("\n")
        elif tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "tr"):
            # Block elements get a newline before them
            parts.append("\n")
            parts.append(_get_element_text(child))
            if child.tail:
                parts.append(child.tail)
        else:
            parts.append(_get_element_text(child))
            if child.tail:
                parts.append(child.tail)
    return "".join(parts)


def load_txt(file_path: str) -> list[dict]:
    for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        raise ValueError("无法识别文件编码，请确认文件格式")
    if not text.strip():
        raise ValueError("文件内容为空")
    return [{
        "content": text.strip(),
        "metadata": {"source": file_path}
    }]


def load_document(file_path: str) -> list[dict]:
    ext = Path(file_path).suffix.lower()
    try:
        if ext == ".pdf":
            return load_pdf(file_path)
        elif ext in (".docx", ".doc"):
            return load_docx(file_path)
        elif ext in (".txt", ".md"):
            return load_txt(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"文件解析失败: {str(e)}")
