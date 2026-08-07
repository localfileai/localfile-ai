"""문서 텍스트 추출. (BE2)

PyMuPDF로 PDF·TXT·Markdown에서 본문을 뽑습니다.
전체를 읽으면 느려지므로 첫 페이지 기준으로 자릅니다 (기본 1,500자).

MVP 범위 밖: 스캔 PDF, 이미지, OCR, HWP, DOCX, PPTX.
"""
