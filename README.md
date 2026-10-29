# Loucks History

A local family archive for documents and genealogy. Built with Python's standard library; no packages, accounts, or external services are required.

## Start

From this repository, with Python 3.12 or newer:

```sh
python -m loucks_history
```

The server listens on `127.0.0.1`, port `8000`. In a local development session, open that address in your browser. Cloud onboarding does not provide a browser preview. To use the archive on your own computer, clone this repository there and run the same command.

Add family members with names, dates, birthplaces, life stories, and up to two parent links. Add parents before children. Upload original documents (up to 15 MB each), categorize them, record their sources, and link them to family members. Search records and explore a timeline of recorded birth and death dates. Original files are downloaded as attachments rather than rendered inline.

## Privacy and storage

This is a **local prototype**, without user accounts, online sharing, editing, or deletion. Do not expose its port to the Internet or deploy it as a private hosted service without authentication, authorization, HTTPS, and a backup plan. Anyone with access to the local server can read and add records. The app makes no external requests and uses no analytics or remote fonts.

Records are in `.history-data/archive.sqlite3`; original uploads are in `.history-data/documents/`. This directory is ignored by Git. Files are not encrypted by this app. Use a trusted machine with appropriate disk security. Application access logs omit request paths and family details.

For a backup, stop the server and copy the **entire** `.history-data` directory to a secure location. Restore the complete directory while the server is stopped. A code commit or environment snapshot is not a private archive backup. Do not publish an environment snapshot containing real family data without understanding who can access it. For storage outside the checkout, use `LOUCKS_DATA_DIR` or `--data-dir /path/to/private/storage`.

## Verify

```sh
python -m unittest discover -s tests -v
```

The tests use temporary storage and synthetic records. They exercise real HTTP requests for family relationships, upload/download integrity, validation, local access restrictions, and static pages.

## Starting material

`Presentation1.pptx` is the original uploaded presentation. It has not been imported as a family archive record. No family facts or sample people have been invented.
