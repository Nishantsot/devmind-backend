import os
import numpy as np

from pypdf import PdfReader
from sentence_transformers import SentenceTransformer


# =========================================================
# EMBEDDING MODEL - LAZY LOAD
# =========================================================

embedding_model = None


def get_embedding_model():
    global embedding_model

    if embedding_model is None:
        embedding_model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

    return embedding_model


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

    model = get_embedding_model()

    embeddings = model.encode(
        chunks,
        normalize_embeddings=True,
    )

    documents[
        document_id
    ] = {
        "chunks": chunks,
        "embeddings": embeddings,
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

    model = get_embedding_model()

    query_embedding = model.encode(
        [query],
        normalize_embeddings=True,
    )[0]

    embeddings = document[
        "embeddings"
    ]

    scores = np.dot(
        embeddings,
        query_embedding,
    )

    top_indexes = (
        np.argsort(scores)
        [::-1][:top_k]
    )

    results = []

    for index in top_indexes:

        results.append(
            {
                "text":
                    document[
                        "chunks"
                    ][index],

                "score":
                    float(
                        scores[index]
                    ),
            }
        )

    return results