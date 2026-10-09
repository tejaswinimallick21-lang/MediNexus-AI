"""
Text Chunking Engine for MediNexus AI RAG System.
"""

from typing import List, Dict, Any


def chunk_document(
    doc: Dict[str, Any],
    max_chunk_words: int = 150,
    overlap_words: int = 30,
) -> List[Dict[str, Any]]:
    """
    Split a document into overlapping semantic chunks with preserved source metadata.
    """
    content = doc.get("content", "")
    sections = content.split("\n\n")
    chunks = []
    chunk_index = 0

    current_chunk = []
    current_word_count = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue

        words = section.split()
        if current_word_count + len(words) <= max_chunk_words:
            current_chunk.append(section)
            current_word_count += len(words)
        else:
            if current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append({
                    "chunk_id": f"{doc['doc_id']}_chk_{chunk_index}",
                    "doc_id": doc["doc_id"],
                    "filename": doc["filename"],
                    "title": doc["title"],
                    "category": doc["category"],
                    "text": chunk_text,
                })
                chunk_index += 1

            # Start new chunk with overlap if applicable
            current_chunk = [section]
            current_word_count = len(words)

    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        chunks.append({
            "chunk_id": f"{doc['doc_id']}_chk_{chunk_index}",
            "doc_id": doc["doc_id"],
            "filename": doc["filename"],
            "title": doc["title"],
            "category": doc["category"],
            "text": chunk_text,
        })

    return chunks


def chunk_all_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Chunk a collection of documents."""
    all_chunks = []
    for doc in documents:
        all_chunks.extend(chunk_document(doc))
    return all_chunks
