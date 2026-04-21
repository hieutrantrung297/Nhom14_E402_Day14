"""
Knowledge base: đọc 5 tài liệu thực tế từ thư mục docs của Day08.
Mỗi document có id, title, content (full text).
"""

import os

_DOCS_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "Lecture-Day-08-09-10",
    "day08",
    "lab",
    "data",
    "docs",
)

_DOC_META = [
    {"id": "access_control_sop", "title": "Quy trình kiểm soát truy cập hệ thống", "file": "access_control_sop.txt"},
    {"id": "hr_leave_policy",    "title": "Chính sách nghỉ phép và phúc lợi nhân sự",  "file": "hr_leave_policy.txt"},
    {"id": "it_helpdesk_faq",   "title": "IT Helpdesk FAQ",                             "file": "it_helpdesk_faq.txt"},
    {"id": "policy_refund_v4",  "title": "Chính sách hoàn tiền phiên bản 4",            "file": "policy_refund_v4.txt"},
    {"id": "sla_p1_2026",       "title": "SLA Ticket – Quy định xử lý sự cố",           "file": "sla_p1_2026.txt"},
]


def _load_documents() -> list[dict]:
    docs = []
    for meta in _DOC_META:
        path = os.path.join(_DOCS_DIR, meta["file"])
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            content = f"[Không tìm thấy file: {meta['file']}]"
        docs.append({"id": meta["id"], "title": meta["title"], "content": content})
    return docs


DOCUMENTS: list[dict] = _load_documents()
DOC_INDEX: dict[str, dict] = {d["id"]: d for d in DOCUMENTS}


def get_doc(doc_id: str) -> dict:
    return DOC_INDEX.get(doc_id, {})


def get_all_docs() -> list[dict]:
    return DOCUMENTS
