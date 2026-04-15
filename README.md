# LangChain RAG for COI / gPlant Data

This project is a local document RAG prototype for querying COI and gPlant analysis materials.
It combines structured table lookup for exact experimental results with LangChain-based retrieval for document questions.

## Main Features

- Ask questions from the command line after running `main.py`.
- Query local documents under `data/`.
- Support PDF, DOCX, HTML, Excel, CSV/TSV, FASTA, and text files.
- Use direct Excel lookup for ASV, species, read count, and identity questions.
- Use LangChain + OpenAI embeddings for general document retrieval.
- Restrict GPT answers to the retrieved document context.
- Keep `.env`, virtual environments, and local vector indexes out of Git.

## Environment

Recommended Python version: Python 3.11.

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

The `.env` file is ignored by Git and should not be uploaded.

## Usage

Check configuration and local documents:

```bash
python main.py --dry-run
```

Run interactive question answering:

```bash
python main.py
```

Ask one question directly:

```bash
python main.py "COI の ASV_002 は何の生物種で、read 数はいくつですか？"
```

Force rebuilding the local vector index:

```bash
python main.py --rebuild-index
```

Show retrieved chunks for debugging:

```bash
python main.py "この研究の目的と方法を説明してください。" --debug
```

## Data Layout

```text
data/
├─ 01_knowledge_docs
├─ 02_tables
├─ 03_reports
├─ 04_sequences_fasta
├─ 05_raw_reads_fastq
├─ 06_qiime2_artifacts
└─ 07_images
```

## Notes

- Exact ASV/read/species queries are handled by direct table lookup when possible.
- General document questions use retrieved context from local files.
- GPT is instructed not to use outside knowledge when generating RAG answers.
- The local vector index is stored in `.rag_index/` and is not committed.
