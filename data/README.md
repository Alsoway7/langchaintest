# Data layout

This directory is organized by how each file should be used in the RAG and analysis workflow.

- `01_knowledge_docs/`: thesis, field notes, slides, and other narrative documents.
- `02_tables/`: structured result tables such as TSV, CSV, and Excel files.
- `03_reports/`: HTML reports, delivery notes, logs, maps, and other text reports.
- `04_sequences_fasta/`: representative FASTA sequences.
- `05_raw_reads_fastq/`: raw FASTQ files. These are preserved but skipped by the RAG loader.
- `06_qiime2_artifacts/`: QIIME2 `.qza` and `.qzv` files. These are preserved but skipped by the RAG loader unless exported to text/table formats.
- `07_images/`: figures and images. These are preserved but skipped by the text RAG loader.

`file_catalog.csv` records where each file came from and where it was moved.
