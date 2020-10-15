from django.db import models
from gcloudc.db.models.fields.iterable import (
    ListField,
)

from gcloudc.db.models.fields.related import RelatedSetField
from gcloudc.db.models.fields.json import JSONField

from .document import Document

WORD_DOCUMENT_JOIN_STRING = "|"


class DocumentRecord(models.Model):
    """
        'Document' is intentionally not a model;
        it would ruin the abstraction, and we need to
        store all kinds of data related to a Document.
        So instead, each Document has an instance of DocumentRecord
        this is the closest to a database representation of the doc
        and indeed, is where the document ID comes from.

        DocumentRecord exists to keep a reference to all word indexes
        and any stats/settings about the document (e.g. its rank).
    """
    index_stats = models.ForeignKey("IndexStats", on_delete=models.CASCADE)

    # This allows for up-to 10000 unique terms in a single
    # document. We need this data when deleting a document
    # from the index
    word_field_indexes = RelatedSetField("WordFieldIndex")

    # This is the data at the time the field was indexed so the doc
    # can be reconstructed on fetch
    data = JSONField()


class WordFieldIndex(models.Model):
    # key should be of the format WWWW|XXXX|YYYY|ZZZZ where:
    # WWWW = index ID
    # XXXX = field_name
    # YYYY = normalised word
    # ZZZZ = document id

    # Querying for documents or fields containing the word
    # will just be a key__startswith query (effectively)
    id = models.CharField(primary_key=True, max_length=100, default=None)

    index_stats = models.ForeignKey("IndexStats", on_delete=models.CASCADE)
    record = models.ForeignKey("DocumentRecord", on_delete=models.CASCADE)
    word = models.CharField(max_length=500)
    field_name = models.CharField(max_length=500)

    # List of indexes into field content where this word occurs
    # This is used when searching for phrases
    occurrences = ListField(models.IntegerField(), blank=False)

    @classmethod
    def document_id_from_pk(cls, pk):
        """
            Given a PK in the right format, return the document ID
        """
        if pk is None:
            return None

        return int(pk.split(WORD_DOCUMENT_JOIN_STRING)[-1])

    @property
    def document_id(self):
        return self.record_id

    @property
    def document(self):
        return Document.objects.get(pk=self.document_id)

    def save(self, *args, **kwargs):
        orig_pk = self.pk

        self.pk = WORD_DOCUMENT_JOIN_STRING.join(
            [str(x) for x in (self.index_stats_id, self.word, self.field_name, self.document_id)]
        )

        # Just check that we didn't *change* the PK
        assert((orig_pk is None) or orig_pk == self.pk)
        super().save(*args, **kwargs)


class IndexStats(models.Model):
    """
        This is a representation of the index
        in the datastore. Its PK is used as
        a prefix to documents and word tables
        but it's only really used itself to maintain
        statistics about the indexed data.
    """

    name = models.CharField(max_length=100, unique=True)
    document_count = models.PositiveIntegerField(default=0)