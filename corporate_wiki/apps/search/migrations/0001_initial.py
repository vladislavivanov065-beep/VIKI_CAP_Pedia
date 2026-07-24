from django.db import migrations

# A standalone FTS5 virtual table, not a real Django model: Article's
# primary key is a UUID, and FTS5's efficient "external content" mode
# requires the content table to have an INTEGER rowid-compatible PK, so
# the article id is instead stored as a plain UNINDEXED text column and
# kept in sync from a post_save signal on Article (see apps/search/fts.py
# and apps/search/apps.py) rather than SQL triggers.
#
# The 'unicode61' tokenizer case-folds Cyrillic (and other Unicode
# letters) at the C level, unlike SQLite's LOWER()/LIKE which only fold
# ASCII -- this is what actually fixes the Cyrillic case-insensitivity
# problem, not just a performance improvement.
CREATE_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    article_id UNINDEXED,
    title,
    content,
    tokenize = 'unicode61'
);
"""

DROP_FTS_TABLE = "DROP TABLE IF EXISTS articles_fts;"

# Exposes the FTS5 index's tokenized vocabulary as a queryable table --
# used to build "did you mean" typo suggestions without maintaining a
# separate word list.
CREATE_VOCAB_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts_vocab USING fts5vocab(articles_fts, 'row');
"""

DROP_VOCAB_TABLE = "DROP TABLE IF EXISTS articles_fts_vocab;"


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(CREATE_FTS_TABLE, reverse_sql=DROP_FTS_TABLE),
        migrations.RunSQL(CREATE_VOCAB_TABLE, reverse_sql=DROP_VOCAB_TABLE),
    ]
