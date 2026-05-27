from docx import Document
doc = Document('260527　RAGハチミツデータ簡単な質問＿fastaファイル数について修正.docx')
for i, para in enumerate(doc.paragraphs):
    if para.text.strip():
        print(f'[{i}] {para.text}')
