#!/usr/bin/env python3
"""
One-time migration: converts products.description from TEXT to JSON.

Plain-text descriptions are wrapped into a minimal TipTap paragraph doc.
Descriptions that are already valid JSON objects (TipTap format) are cast
directly to JSON. NULL / empty values stay NULL.

Run from the backend root:
    python scripts/migrate_description_to_json.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.database import engine


def run():
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE products
            ALTER COLUMN description TYPE JSON
            USING
                CASE
                    WHEN description IS NULL OR TRIM(description) = ''
                        THEN NULL
                    WHEN TRIM(description) LIKE '{%'
                        THEN description::json
                    ELSE json_build_object(
                        'type', 'doc',
                        'content', json_build_array(
                            json_build_object(
                                'type', 'paragraph',
                                'content', json_build_array(
                                    json_build_object(
                                        'type', 'text',
                                        'text', description
                                    )
                                )
                            )
                        )
                    )
                END
        """))

    print("Done — products.description column is now JSON.")
    print("Existing plain-text descriptions have been wrapped as TipTap paragraph nodes.")


if __name__ == "__main__":
    run()
