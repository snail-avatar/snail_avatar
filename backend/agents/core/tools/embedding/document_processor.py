# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : document_processor.py
# @Desc    : 文档处理器（PDF解析、图片提取、OCR）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
文档处理器基类

支持：
- 普通PDF：提取文本 + 嵌入图片
- 扫描件PDF：OCR识别文本 + 整页图片向量化
- 纯图片：直接读取 + 可选OCR
- 纯文本：按段落拆分
"""

import os
from typing import List, Optional

from .data_types import DocumentChunk
from snail_avatar.backend.core.work_log import WorkLogger


class DocumentProcessor:
    """文档处理器，将PDF/图片拆分为 DocumentChunk 列表"""

    def __init__(self, config: dict = None, progress_callback=None):
        """
        Args:
            config: 配置字典，包含 document_processor 相关参数
            progress_callback: 进度回调函数，签名: callback(current, total, message)
        """
        self._config = config or {}
        self._ocr_lang = self._config.get("ocr_lang", "chi_sim+eng")
        self._max_chunk_size = self._config.get("max_chunk_size", 2000)
        self._scanned_threshold = self._config.get("scanned_threshold", 100)
        self._scanned_check_pages = self._config.get("scanned_check_pages", 3)
        self._ocr_reader = None
        self._progress_callback = progress_callback

    def _get_ocr_reader(self):
        """获取 EasyOCR Reader（延迟初始化）"""
        if self._ocr_reader is None:
            try:
                import easyocr
                langs = []
                if 'chi' in self._ocr_lang:
                    langs.append('ch_sim')
                if 'eng' in self._ocr_lang:
                    langs.append('en')
                if not langs:
                    langs = ['ch_sim', 'en']
                WorkLogger.info(f"[DocumentProcessor] 初始化 EasyOCR (语言: {langs})...")
                self._ocr_reader = easyocr.Reader(langs, gpu=False)
                WorkLogger.info("[DocumentProcessor] EasyOCR 初始化完成")
            except Exception as e:
                WorkLogger.warn(f"[DocumentProcessor] EasyOCR 初始化失败: {e}")
                self._ocr_reader = None
        return self._ocr_reader

    def process_file(self, file_path: str, progress_callback=None) -> List[DocumentChunk]:
        """处理文件入口，自动判断文件类型
        
        Args:
            file_path: 文件路径
            progress_callback: 进度回调函数（可选），覆盖初始化时的回调
        """
        original_callback = self._progress_callback
        if progress_callback:
            self._progress_callback = progress_callback
        
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            result = self.process_pdf(file_path)
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"):
            result = self.process_image(file_path)
        elif ext in (".txt", ".md"):
            result = self.process_text(file_path)
        else:
            WorkLogger.warn(f"[DocumentProcessor] 不支持的文件类型: {ext}")
            result = []
        
        self._progress_callback = original_callback
        return result

    def process_pdf(self, file_path: str) -> List[DocumentChunk]:
        """处理PDF文件"""
        chunks = []
        source_name = os.path.basename(file_path)
        if self._is_scanned_pdf(file_path):
            chunks = self._process_scanned_pdf(file_path, source_name)
        else:
            chunks = self._process_normal_pdf(file_path, source_name)
        return chunks

    def process_image(self, file_path: str) -> List[DocumentChunk]:
        """处理纯图片文件"""
        source_name = os.path.basename(file_path)
        img_base64 = self._image_to_base64(file_path)
        if img_base64 is None:
            return []
        text = self._ocr_image(file_path) or f"[图片: {source_name}]"
        chunk = DocumentChunk(
            text=text,
            images=[img_base64],
            metadata={
                "source": source_name,
                "type": "image",
                "file_path": file_path,
            },
        )
        return [chunk]

    def process_text(self, file_path: str) -> List[DocumentChunk]:
        """处理纯文本文件"""
        source_name = os.path.basename(file_path)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            WorkLogger.error(f"[DocumentProcessor] 读取文本文件失败: {e}")
            return []
        if not content.strip():
            return []
        paragraphs = self._split_text(content)
        chunks = []
        for i, para in enumerate(paragraphs):
            if not para.strip():
                continue
            chunks.append(DocumentChunk(
                text=para.strip(),
                metadata={
                    "source": source_name,
                    "type": "text",
                    "paragraph": i + 1,
                    "file_path": file_path,
                },
            ))
        return chunks

    def process_directory(self, dir_path: str) -> List[DocumentChunk]:
        """处理整个目录下的所有支持文件"""
        all_chunks = []
        for root, dirs, files in os.walk(dir_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext in (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".txt", ".md"):
                    WorkLogger.info(f"[DocumentProcessor] 处理: {fname}")
                    chunks = self.process_file(fpath)
                    all_chunks.extend(chunks)
        return all_chunks

    def _is_scanned_pdf(self, file_path: str) -> bool:
        """判断PDF是否为扫描件"""
        try:
            import PyPDF2
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                total_text = ""
                for i in range(min(self._scanned_check_pages, len(reader.pages))):
                    page = reader.pages[i]
                    text = page.extract_text()
                    if text:
                        total_text += text
                return len(total_text.strip()) < self._scanned_threshold
        except Exception as e:
            WorkLogger.warn(f"[DocumentProcessor] PDF判断失败，默认按扫描件处理: {e}")
            return True

    def _process_normal_pdf(self, file_path: str, source_name: str) -> List[DocumentChunk]:
        """处理普通PDF：提取文本 + 嵌入图片（使用PyMuPDF统一处理所有图片格式）"""
        chunks = []
        try:
            import PyPDF2
            import fitz
            from PIL import Image
            import io
            import base64

            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                pdf_texts = {}
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text()
                    if text and text.strip():
                        pdf_texts[page_num] = text

            doc = fitz.open(file_path)
            pdf_images = {}
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)
                
                images_b64 = []
                for img_index, img_info in enumerate(image_list):
                    xref = img_info[0]
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        
                        img = None
                        
                        if pix.colorspace is None:
                            try:
                                mode = "L" if pix.n <= 2 else "RGB"
                                img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                            except Exception as e:
                                WorkLogger.warn(f"NULL颜色空间提取失败 [p{page_num+1}/img{img_index}]: {e}")
                                continue
                        else:
                            if pix.n >= 3:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            elif pix.n == 2:
                                pix = fitz.Pixmap(fitz.csGRAY, pix)
                            
                            if pix.alpha > 0:
                                pix = fitz.Pixmap(pix, 0)
                            
                            try:
                                img_bytes = pix.tobytes("png")
                                img = Image.open(io.BytesIO(img_bytes))
                            except Exception:
                                try:
                                    mode = "L" if pix.n == 1 else "RGB"
                                    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                                except Exception as e2:
                                    WorkLogger.warn(f"图片提取失败 [p{page_num+1}/img{img_index}]: {e2}")
                                    continue
                        
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        
                        max_size = 800
                        width, height = img.size
                        new_width, new_height = width, height
                        if width > max_size or height > max_size:
                            if width > height:
                                new_width = max_size
                                new_height = int(height * max_size / width)
                            else:
                                new_height = max_size
                                new_width = int(width * max_size / height)
                            img = img.resize((new_width, new_height), Image.LANCZOS)
                        
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=85)
                        img_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
                        images_b64.append(img_b64)
                        
                        WorkLogger.info(f"提取图片 [p{page_num+1}/img{img_index}]: {width}x{height} -> {new_width}x{new_height}, {len(img_b64)//1024}KB")
                        
                    except Exception as e:
                        WorkLogger.warn(f"图片提取失败 [p{page_num+1}/img{img_index}]: {e}")
                
                pdf_images[page_num + 1] = images_b64
            
            doc.close()

            for page_num in sorted(pdf_texts.keys()):
                text = pdf_texts[page_num]
                images_b64 = pdf_images.get(page_num, [])
                
                paragraphs = self._split_text(text)
                for para in paragraphs:
                    if not para.strip():
                        continue
                    chunks.append(DocumentChunk(
                        text=para.strip(),
                        images=images_b64 if images_b64 else [],
                        metadata={
                            "source": source_name,
                            "type": "pdf_text",
                            "page": page_num,
                            "file_path": file_path,
                        },
                    ))

        except Exception as e:
            WorkLogger.error(f"[DocumentProcessor] 处理普通PDF失败: {e}")
        return chunks

    def _process_scanned_pdf(self, file_path: str, source_name: str) -> List[DocumentChunk]:
        """处理扫描件PDF：OCR识别文本 + 整页图片向量化（使用PyMuPDF替代pdf2image）"""
        chunks = []
        try:
            import fitz
            import numpy as np
            import cv2
            from PIL import Image
            import base64, io

            doc = fitz.open(file_path)
            total_pages = len(doc)
            reader = self._get_ocr_reader()

            for page_num in range(total_pages):
                if self._progress_callback:
                    self._progress_callback(page_num + 1, total_pages, 
                        f"OCR识别第{page_num+1}/{total_pages}页")
                
                page = doc[page_num]
                
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"

                text = ""
                if reader:
                    try:
                        img_array = np.array(img.convert('RGB'))
                        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                        result = reader.readtext(img_bgr)
                        texts = [item[1] for item in result if item[1].strip()]
                        text = ' '.join(texts)
                    except Exception as e:
                        WorkLogger.warn(f"[DocumentProcessor] OCR失败 (第{page_num+1}页): {e}")

                if not text or not text.strip():
                    text = f"[扫描件第{page_num+1}页，无识别文本]"

                chunks.append(DocumentChunk(
                    text=text.strip(),
                    images=[img_b64],
                    metadata={
                        "source": source_name,
                        "type": "scanned_pdf",
                        "page": page_num + 1,
                        "file_path": file_path,
                    },
                ))
            
            doc.close()
        except Exception as e:
            WorkLogger.error(f"[DocumentProcessor] 处理扫描件PDF失败: {e}")
        return chunks

    def _ocr_image(self, image_path: str) -> Optional[str]:
        """对图片执行 OCR"""
        try:
            reader = self._get_ocr_reader()
            if reader is None:
                return None
            import numpy as np
            from PIL import Image
            img = Image.open(image_path)
            img_array = np.array(img.convert('RGB'))
            img_bgr = img_array[:, :, ::-1]
            result = reader.readtext(img_bgr)
            texts = [item[1] for item in result if item[1].strip()]
            return ' '.join(texts) if texts else None
        except Exception as e:
            WorkLogger.warn(f"[DocumentProcessor] OCR失败: {e}")
            return None

    @staticmethod
    def _image_to_base64(image_path: str) -> Optional[str]:
        """图片转base64"""
        try:
            import base64
            from PIL import Image
            import io

            with Image.open(image_path) as img:
                ext = os.path.splitext(image_path)[1].lower().replace(".", "")
                if ext == "jpg":
                    ext = "jpeg"
                buf = io.BytesIO()
                img.save(buf, format=ext.upper())
                return f"data:image/{ext};base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
        except Exception as e:
            WorkLogger.warn(f"[DocumentProcessor] 图片读取失败: {e}")
            return None

    def _split_text(self, text: str) -> List[str]:
        """按段落拆分文本"""
        paragraphs = text.split("\n\n")
        result = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(para) > self._max_chunk_size:
                sentences = para.replace("。", "。\n").replace(".\n", ".\n").split("\n")
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) > self._max_chunk_size and current:
                        result.append(current.strip())
                        current = sent
                    else:
                        current += sent
                if current.strip():
                    result.append(current.strip())
            else:
                result.append(para)

        return result