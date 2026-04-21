"""
Document Chunker: chia tài liệu thành các chunk nhỏ có overlap.
Chiến lược: line-aware chunking — giữ ranh giới dòng tự nhiên,
ghép các dòng ngắn lại, cắt khi đủ chunk_size.
"""

from typing import List, Dict


def chunk_document(
    doc: Dict,
    chunk_size: int = 400,
    overlap: int = 80,
) -> List[Dict]:
    """
    Chia 1 document thành các chunk.

    Args:
        doc: {"id", "title", "content"}
        chunk_size: số ký tự tối đa mỗi chunk
        overlap: số ký tự lấy lại từ chunk trước (sliding window)

    Returns:
        List[{"chunk_id", "doc_id", "title", "text"}]
    """
    lines = [l.strip() for l in doc["content"].split("\n") if l.strip()]
    chunks: List[str] = []
    current = ""

    for line in lines:
        if not current:
            current = line
        elif len(current) + len(line) + 1 <= chunk_size:
            current += "\n" + line
        else:
            chunks.append(current)
            # Overlap: lấy phần cuối của chunk vừa lưu
            if overlap > 0 and len(current) > overlap:
                tail = current[-overlap:]
                # Tìm ranh giới từ gần nhất
                sp = tail.find(" ")
                current = (tail[sp + 1:] if sp != -1 else tail) + "\n" + line
            else:
                current = line

    if current:
        chunks.append(current)

    return [
        {
            "chunk_id": f"{doc['id']}_c{i:03d}",
            "doc_id": doc["id"],
            "title": doc["title"],
            "text": chunk,
        }
        for i, chunk in enumerate(chunks)
    ]


def chunk_all_docs(
    docs: List[Dict],
    chunk_size: int = 400,
    overlap: int = 80,
) -> List[Dict]:
    """Chunk toàn bộ knowledge base."""
    all_chunks = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc, chunk_size, overlap))
    return all_chunks


if __name__ == "__main__":
    from data.knowledge_base import get_all_docs
    chunks = chunk_all_docs(get_all_docs())
    print(f"Total chunks: {len(chunks)}")
    for c in chunks:
        print(f"  {c['chunk_id']} ({len(c['text'])} chars)")
