# Báo cáo Phân tích Thất bại (Failure Analysis Report)

## 1. Tổng quan Benchmark

| Chỉ số | Agent V1 (Base) | Agent V2 (Optimized) |
|--------|-----------------|----------------------|
| Tổng cases | 60 | 60 |
| Pass / Fail | 55 / 5 (91.7%) | 53 / 7 (88.3%) |
| Avg Judge Score | 4.342 / 5.0 | 4.383 / 5.0 |
| Hit Rate @3 | 98.3% | 100.0% |
| MRR | 0.903 | 0.983 |
| Faithfulness | 0.982 | 0.883 |
| Relevancy | — | 0.909 |
| Agreement Rate | 100.0% | 100.0% |
| Avg Latency | 2.94s | 5.81s |
| Total Cost | $0.0813 | $0.0655 |
| Cost / Case | $0.001355 | $0.001092 |

**Kết quả Regression Gate:** APPROVE — V2 cải thiện +0.041 điểm so với V1.

**Phân phối điểm (V2):**
| Score | Số cases | % |
|-------|----------|---|
| 5.0 | 36 | 60.0% |
| 4.0 – 4.5 | 14 | 23.3% |
| 3.0 – 3.5 | 2 | 3.3% |
| 1.0 – 2.5 | 8 | 13.3% |

---

## 2. Phân nhóm lỗi (Failure Clustering)

| Nhóm lỗi | Số cases | Case IDs | Nguyên nhân |
|----------|----------|----------|-------------|
| Generation sai hoàn toàn dù Retrieval đúng | 2 | tc_041, tc_042 | LLM không trích xuất được số liệu cụ thể từ chunk |
| Tính toán / Suy luận đa bước | 2 | tc_052, tc_054 | LLM tính sai ngày, số khi cần arithmetic |
| Câu hỏi mơ hồ / thiếu context | 2 | tc_051, tc_058 | Câu hỏi không đủ thông tin để agent trả lời chính xác |
| Out-of-context và Adversarial | 2 | tc_056, tc_057 | Agent từ chối đúng nhưng thiếu hướng dẫn bổ sung |
| Thiếu chi tiết trong câu trả lời | 1 | tc_053 | Đúng ý chính nhưng bỏ sót thông số SLA cụ thể |

**Nhận xét quan trọng:** Hit Rate = 100% — tất cả 9 fail/low-score cases đều có Retrieval đúng tài liệu. Vấn đề nằm hoàn toàn ở **Generation stage**, không phải Retrieval.

---

## 3. Phân tích 5 Whys (3 case tệ nhất)

### Case #1 — tc_041 & tc_042 (Score: 1.0 — Tệ nhất)
**Câu hỏi:** "SLA quy định ticket P1 phải được phản hồi / giải quyết trong bao lâu?"
**Câu trả lời Agent:** "Tôi không tìm thấy thông tin này trong tài liệu."

1. **Symptom:** Agent trả lời sai hoàn toàn — nói không có thông tin trong khi tài liệu `sla_p1_2026` đã được retrieve đúng (hit_rate=1.0, mrr=1.0).
2. **Why 1:** Agent nhận được context từ đúng tài liệu nhưng vẫn báo "không tìm thấy thông tin".
3. **Why 2:** Chunk được retrieve chứa doc_id đúng (`sla_p1_2026`) nhưng nội dung chunk đó không chứa con số SLA cụ thể (thời gian phản hồi/giải quyết).
4. **Why 3:** Chunking strategy chia cắt tài liệu SLA theo ranh giới dòng — con số quan trọng (ví dụ "15 phút", "4 giờ") nằm ở chunk khác với phần mô tả P1, bị cắt rời.
5. **Why 4:** top_k=2 (V2) không đủ để bao phủ cả chunk định nghĩa và chunk con số, trong khi top_k=3 (V1) vẫn gặp vấn đề tương tự.
6. **Root Cause:** **Chunking strategy** chia cắt semantic unit — thông tin SLA (định nghĩa + số liệu) bị tách sang hai chunk khác nhau. Vector search chỉ lấy chunk có semantic similarity cao nhất (phần định nghĩa) mà bỏ qua chunk chứa con số cụ thể.

**Fix đề xuất:** Dùng semantic chunking hoặc tăng chunk_size để giữ nguyên một section SLA; hoặc tăng top_k lên 5 để đảm bảo bao phủ cả hai chunk.

---

### Case #2 — tc_052 (Score: 1.5 — Tính toán sai)
**Câu hỏi:** "Nhân viên 6 năm kinh nghiệm năm ngoái dùng 13 ngày phép. Năm nay có tối đa bao nhiêu ngày phép?"
**Câu trả lời Agent:** Tính sai số ngày chuyển từ năm trước và số ngày phép tổng cộng.

1. **Symptom:** Agent trích xuất được chính sách phép năm đúng nhưng tính toán số học sai.
2. **Why 1:** Câu hỏi yêu cầu multi-step arithmetic: (1) tra cứu số ngày phép theo số năm kinh nghiệm, (2) tính số ngày còn dư năm ngoái, (3) cộng thêm năm nay.
3. **Why 2:** System prompt chỉ yêu cầu agent "trả lời ngắn gọn, chính xác dựa trên context" — không có hướng dẫn cụ thể về cách xử lý bài toán số học.
4. **Why 3:** gpt-4o-mini có xu hướng mắc lỗi arithmetic khi không được nhắc suy luận từng bước (chain-of-thought).
5. **Root Cause:** **Prompting strategy** thiếu chain-of-thought cho các câu hỏi cần tính toán; kết hợp với giới hạn max_tokens=512 khiến agent không suy luận đầy đủ.

**Fix đề xuất:** Thêm câu "Nếu cần tính toán, hãy thực hiện từng bước trước khi đưa ra kết quả cuối" vào system prompt. Hoặc tăng max_tokens lên 1024.

---

### Case #3 — tc_054 (Score: 2.5 — Suy luận ngày tháng sai)
**Câu hỏi:** "Tôi mua sản phẩm ngày 05/02/2026 nhưng bị lỗi nhà sản xuất, hôm nay là 15/02/2026. Tôi có được hoàn tiền không?"
**Câu trả lời Agent:** Kết luận sai — báo không được hoàn tiền trong khi thực tế đủ điều kiện theo policy.

1. **Symptom:** Agent áp dụng sai điều khoản trong policy hoàn tiền, dẫn đến kết luận ngược với thực tế.
2. **Why 1:** Câu hỏi yêu cầu so sánh ngày (05/02 → 15/02 = 10 ngày) với ngưỡng trong policy (7 ngày làm việc vs. 30 ngày cho lỗi nhà sản xuất).
3. **Why 2:** Policy có nhiều điều khoản khác nhau cho các trường hợp khác nhau (thông thường vs. lỗi nhà sản xuất) — agent áp dụng nhầm điều khoản thông thường thay vì điều khoản lỗi nhà sản xuất.
4. **Why 3:** Chunk retrieved chứa điều khoản tổng quát, không chứa điều khoản đặc biệt cho "lỗi nhà sản xuất" hoặc cả hai điều khoản nằm ở các vị trí khác nhau trong tài liệu.
5. **Root Cause:** **Chunking** cắt rời các điều khoản liên quan trong cùng một chính sách. Agent chỉ nhìn thấy một phần của policy, áp dụng sai trường hợp.

**Fix đề xuất:** Parent-document retrieval — khi chunk của `policy_refund_v4` được match, expand context sang các chunk lân cận để đảm bảo agent thấy đủ toàn bộ section liên quan.

---

## 4. Kết luận Root Cause tổng thể

**Tất cả failures đều xảy ra khi Retrieval đúng (Hit Rate = 100%)** — đây là dấu hiệu rõ ràng rằng vấn đề không nằm ở Vector Search mà nằm ở 2 tầng:

| Tầng | Vấn đề | Số cases bị ảnh hưởng |
|------|--------|----------------------|
| **Chunking** | Cắt rời semantic unit, tách thông tin liên quan sang chunk khác | 4/9 (tc_041, tc_042, tc_054, tc_051) |
| **Prompting/Generation** | LLM tính toán sai, áp dụng nhầm điều khoản, không có CoT | 3/9 (tc_052, tc_053, tc_054) |
| **Out-of-scope handling** | Từ chối đúng nhưng thiếu hướng dẫn redirect | 2/9 (tc_056, tc_057) |

---

## 5. Kế hoạch cải tiến (Action Plan)

- [x] **Đã làm (V2):** Giảm chunk_size từ 400 xuống 300, giảm top_k từ 3 xuống 2 — cải thiện được +0.041 điểm trung bình.
- [ ] **Chunking:** Thử semantic chunking (chia theo paragraph/section thay vì số ký tự cố định) để giữ nguyên các semantic unit.
- [ ] **Retrieval:** Tăng top_k lên 5, kết hợp parent-document expansion để đảm bảo context đầy đủ cho các câu hỏi phức tạp.
- [ ] **Prompting:** Thêm chain-of-thought instruction cho các câu hỏi có tính toán ("thực hiện từng bước trước khi kết luận").
- [ ] **Out-of-scope:** Cải thiện handling cho câu hỏi ngoài phạm vi — thay vì chỉ nói "không tìm thấy", hướng dẫn người dùng liên hệ đúng bộ phận.
- [ ] **Cost optimization:** Dùng gpt-4o-mini cho cả 2 judge thay vì gpt-4o — tiết kiệm ~95% chi phí judge (~$0.06/run) với mức giảm độ chính xác <5-10%.
