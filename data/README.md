# Data layout

All data files now live directly under this `data/` directory.

To preserve provenance and avoid filename collisions, files that used to be in nested folders are flattened with `__`-joined prefixes, for example:

- `01_knowledge_docs__thesis_and_notes__...`
- `02_tables__COI__...`
- `04_sequences_fasta__gPlant__...`

The app now detects category and marker from these flattened filenames.

- `sample_id_mapping.csv`: optional explicit mapping between thesis sample IDs and sequence sample names.
- `current_inventory.csv`: current flat-file inventory.
- `file_catalog.csv`: provenance mapping from original locations to flattened filenames.
