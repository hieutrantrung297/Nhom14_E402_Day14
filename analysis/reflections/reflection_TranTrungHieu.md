# Báo cáo Cá nhân — Trần Trung Hiếu - 2A202600318
**Lab Day 14: AI Evaluation Factory**
**Nhiệm vụ:** Retrieval Evaluation & Dataset (SDG)

---

## 1. Đóng góp cụ thể (Engineering Contribution)

### 1.1 Dataset & Synthetic Data Generation (`data/synthetic_gen.py`)
Tôi chịu trách nhiệm thiết kế và xây dựng toàn bộ Golden Dataset gồm **60 test cases** với các đặc điểm sau:

- **Phân phối:** 48 easy cases, 7 medium cases, 5 adversarial cases
- **Coverage:** Bao phủ cả 5 tài liệu trong knowledge base (`access_control_sop`, `hr_leave_policy`, `it_helpdesk_faq`, `policy_refund_v4`, `sla_p1_2026`)
- **Ground Truth IDs:** Mỗi test case có trường `expected_retrieval_ids` — danh sách doc_id tài liệu cần được retrieve đúng để tính Hit Rate và MRR
- **Red Teaming cases:** 5 adversarial cases bao gồm: out-of-context queries, prompt injection, câu hỏi mơ hồ, multi-hop reasoning

Quyết định thiết kế quan trọng: Thay vì dùng LLM để sinh test cases (tốn chi phí và khó kiểm soát chất lượng), tôi hardcode 60 cases từ nội dung tài liệu thực để đảm bảo Ground Truth chính xác tuyệt đối.

### 1.2 Retrieval Evaluation (`engine/retrieval_eval.py`, `data/chunker.py`, `data/vector_store.py`)
Tôi xây dựng pipeline đánh giá Retrieval với các thành phần:

**Chunking strategy (`data/chunker.py`):**
- Line-aware chunking: chia theo ranh giới dòng tự nhiên thay vì cắt giữa chừng
- chunk_size=400 chars, overlap=80 chars (V1); chunk_size=300, overlap=60 (V2)
- Kết quả: 37 chunks từ 5 tài liệu

**Vector Store (`data/vector_store.py`):**
- Embed bằng OpenAI `text-embedding-3-small`
- Cosine similarity tìm kiếm qua numpy matrix multiply (L2-normalized vectors)
- Fallback keyword search (BM25-style) khi không có API key

**Retrieval Metrics (`engine/retrieval_eval.py`):**
- **Hit Rate@K:** = 1.0 nếu ít nhất 1 expected doc_id có trong top-K retrieved results
- **MRR (Mean Reciprocal Rank):** = 1/rank của expected doc đầu tiên xuất hiện trong kết quả
- Xử lý đặc biệt: out-of-context cases (expected_ids = []) → tự động cho Hit Rate = 1.0 và MRR = 1.0
- Heuristic faithfulness: token overlap giữa câu trả lời và context retrieved

---

## 2. Kết quả đạt được

| Metric | V1 (top_k=3, chunk=400) | V2 (top_k=2, chunk=300) |
|--------|-------------------------|-------------------------|
| Hit Rate @K | 98.3% | **100.0%** |
| MRR | 0.903 | **0.983** |
| Faithfulness | 0.982 | 0.883 |

V2 cải thiện Hit Rate và MRR đáng kể nhờ chunk nhỏ hơn — các đoạn văn tập trung hơn, embedding semantic chính xác hơn. Tuy nhiên Faithfulness giảm vì top_k=2 cung cấp ít context hơn.

---

## 3. Giải thích kỹ thuật (Technical Depth)

### 3.1 Hit Rate@K là gì?
Hit Rate@K trả lời câu hỏi: "Trong số K chunks được retrieve, có ít nhất 1 chunk đến từ tài liệu đúng không?"

```
Hit Rate = 1.0  nếu  expected_doc_id ∈ retrieved_doc_ids[:K]
Hit Rate = 0.0  nếu  không
```

Đây là metric binary — không phân biệt tài liệu đúng xuất hiện ở vị trí 1 hay vị trí K. Đó là lý do cần MRR.

### 3.2 MRR (Mean Reciprocal Rank) là gì?
MRR đo vị trí của tài liệu đúng trong danh sách kết quả:

```
MRR = mean(1 / rank_i)  với rank_i là vị trí (1-indexed) của tài liệu đúng đầu tiên
```

Ví dụ: Nếu tài liệu đúng xuất hiện ở vị trí 1 → MRR contribution = 1.0; vị trí 2 → 0.5; vị trí 3 → 0.33.

MRR = 0.983 của V2 cho thấy hầu hết câu hỏi đều retrieve đúng tài liệu ở vị trí đầu tiên.

### 3.3 Tại sao Hit Rate = 100% nhưng vẫn có fail cases?
Đây là insight quan trọng nhất từ benchmark: **Retrieval tốt không đảm bảo Generation tốt.**

Hit Rate đo ở cấp độ *document* — tài liệu đúng có trong kết quả. Nhưng trong tài liệu đó có nhiều chunk; agent chỉ nhận được nội dung của K chunks được chọn. Nếu thông tin cụ thể (ví dụ: con số SLA) nằm ở chunk khác với chunk được rank cao nhất, agent sẽ không thấy và trả lời sai — dù Hit Rate vẫn = 1.0.

Đây là lỗi **semantic fragmentation** do chunking strategy — root cause của 4/9 fail cases.

### 3.4 Cohen's Kappa là gì?
Cohen's Kappa (κ) là metric đo mức độ đồng thuận giữa 2 người/model đánh giá, có tính đến xác suất đồng thuận ngẫu nhiên:

```
κ = (P_observed - P_expected) / (1 - P_expected)
```

- κ = 1.0: hoàn toàn đồng thuận
- κ = 0.0: đồng thuận chỉ do ngẫu nhiên
- κ < 0: đồng thuận kém hơn ngẫu nhiên

Hệ thống này dùng **Agreement Rate** (đơn giản hơn) — tỷ lệ cases mà 2 judge cho điểm chênh lệch ≤ 1. Agreement Rate = 100% cho thấy gpt-4o-mini và gpt-4o rất nhất quán trên bộ dataset này.

### 3.5 Position Bias là gì?
Position Bias là hiện tượng LLM-judge có xu hướng ưu tiên câu trả lời xuất hiện ở một vị trí cố định (ví dụ: luôn ưu thích "Response A" hơn "Response B") bất kể nội dung. Hệ thống này kiểm tra bằng cách swap thứ tự A/B và so sánh kết quả.

---

## 4. Khó khăn và cách giải quyết (Problem Solving)

**Vấn đề 1: UnicodeEncodeError trên Windows**
Print statement với ký tự tiếng Việt và emoji gây lỗi cp1252 encoding.
→ Giải pháp: Thay toàn bộ print output bằng ASCII-only text.

**Vấn đề 2: Chunking cắt rời thông tin liên quan**
Phát hiện qua phân tích fail cases: tc_041/tc_042 có Hit Rate=1.0 nhưng score=1.0 vì agent không thấy con số SLA cụ thể.
→ Giải pháp ngắn hạn: Giảm chunk_size (V2). Giải pháp dài hạn: semantic chunking.

**Vấn đề 3: Ground Truth ID mapping cho adversarial cases**
Các câu hỏi out-of-context (lương, thông tin không có trong docs) — không có expected doc_id nào.
→ Giải pháp: expected_retrieval_ids = [] và code xử lý đặc biệt: nếu expected rỗng → Hit Rate = 1.0 (agent không cần retrieve đúng tài liệu nào).

---

## 5. Nhìn lại và rút kinh nghiệm

Điều tôi học được từ lab này:

1. **Retrieval quality ≠ Answer quality.** Metric Hit Rate chỉ đo được một phần của pipeline — cần đánh giá cả Generation stage.
2. **Chunking là quyết định kiến trúc quan trọng nhất.** Chunk quá lớn → thông tin loãng; chunk quá nhỏ → mất context; cả hai đều ảnh hưởng đến Generation.
3. **Golden Dataset chất lượng là nền tảng của mọi thứ.** Nếu Ground Truth sai, mọi metric đều vô nghĩa.
4. **Cost vs Quality trade-off là thực tế:** Giảm top_k từ 3→2 tiết kiệm ~7% tổng chi phí nhưng cải thiện retrieval precision — đây là trade-off có lợi trong trường hợp này.
