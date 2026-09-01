import os
import math
import re
from collections import Counter

from pypdf import PdfReader


# =========================================================
# IN-MEMORY STORE
# =========================================================

documents = {}


# =========================================================
# EXTRACT TEXT
# =========================================================

def extract_text(file_path: str):

    extension = os.path.splitext(
        file_path
    )[1].lower()

    if extension == ".pdf":

        reader = PdfReader(
            file_path
        )

        text = ""

        for page in reader.pages:

            page_text = (
                page.extract_text()
                or ""
            )

            text += (
                page_text
                + "\n"
            )

        return text

    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore",
    ) as file:

        return file.read()


# =========================================================
# CHUNK TEXT
# =========================================================

def chunk_text(
    text: str,
    chunk_size: int = 700,
    overlap: int = 120,
):

    chunks = []

    start = 0

    while start < len(text):

        end = (
            start
            + chunk_size
        )

        chunk = text[
            start:end
        ].strip()

        if chunk:
            chunks.append(
                chunk
            )

        start += (
            chunk_size
            - overlap
        )

    return chunks


# =========================================================
# TOKENIZE
# =========================================================

def tokenize(text: str):

    return re.findall(
        r"[a-zA-Z0-9_]+",
        text.lower(),
    )


# =========================================================
# VECTORIZE
# =========================================================

def vectorize(text: str):

    tokens = tokenize(
        text
    )

    return Counter(
        tokens
    )


# =========================================================
# COSINE SIMILARITY
# =========================================================

def cosine_similarity(
    vector_a,
    vector_b,
):

    common_words = (
        set(vector_a.keys())
        &
        set(vector_b.keys())
    )

    dot_product = sum(
        vector_a[word]
        * vector_b[word]
        for word in common_words
    )

    magnitude_a = math.sqrt(
        sum(
            value * value
            for value in vector_a.values()
        )
    )

    magnitude_b = math.sqrt(
        sum(
            value * value
            for value in vector_b.values()
        )
    )

    if (
        magnitude_a == 0
        or magnitude_b == 0
    ):
        return 0.0

    return (
        dot_product
        /
        (
            magnitude_a
            * magnitude_b
        )
    )


# =========================================================
# INDEX DOCUMENT
# =========================================================

def index_document(
    document_id: str,
    text: str,
):

    chunks = chunk_text(
        text
    )

    if not chunks:
        return 0

    chunk_vectors = []

    for chunk in chunks:

        chunk_vectors.append(
            vectorize(
                chunk
            )
        )

    documents[
        document_id
    ] = {
        "chunks": chunks,
        "vectors": chunk_vectors,
    }

    return len(chunks)


# =========================================================
# SEARCH DOCUMENT
# =========================================================

def search_document(
    document_id: str,
    query: str,
    top_k: int = 4,
):

    document = documents.get(
        document_id
    )

    if not document:
        return []

    query_vector = vectorize(
        query
    )

    scored_results = []

    for index, chunk_vector in enumerate(
        document["vectors"]
    ):

        score = cosine_similarity(
            query_vector,
            chunk_vector,
        )

        scored_results.append(
            (
                index,
                score,
            )
        )

    scored_results.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    top_results = (
        scored_results[:top_k]
    )

    results = []

    for index, score in top_results:

        results.append(
            {
                "text":
                    document[
                        "chunks"
                    ][index],

                "score":
                    float(
                        score
                    ),
            }
        )

    return results