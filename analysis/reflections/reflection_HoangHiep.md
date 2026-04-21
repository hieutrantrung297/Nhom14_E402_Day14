# Báo cáo Cá nhân — Hoàng Hiệp - 2A202600065
**Lab Day 14: AI Evaluation Factory**
**Nhiệm vụ:** Multi-Judge Consensus + Regression Testing (Release Gate)

---

## 1. Đóng góp cụ thể (Engineering Contribution)

### 1.1 Multi-Judge Consensus Engine (`engine/llm_judge.py`)
Tôi phụ trách xây dựng cơ chế chấm điểm bằng nhiều Judge model và hợp nhất kết quả tự động.

- **Triển khai 2 Judge models:** `gpt-4o-mini` (Judge A) và `gpt-4o` (Judge B), chạy song song bằng `asyncio.gather(...)`.
- **Chuẩn hóa output:** ép Judge trả về JSON (`score`, `reasoning`) để tránh lỗi parse khi tổng hợp.
- **Tính độ đồng thuận:** `agreement_rate = 1.0` khi chênh lệch điểm `<= 1`, ngược lại `0.5`.
- **Xử lý xung đột tự động:** nếu chênh lệch `> 1`, kích hoạt `conflict_resolved=True` và lấy điểm thấp hơn (conservative) để giảm rủi ro over-score.
- **Theo dõi chi phí/tokens theo từng Judge:** ghi nhận input/output tokens và cost theo model để phục vụ phân tích trade-off chất lượng/chi phí.
- **Kiểm tra position bias:** có hàm `check_position_bias(...)` theo cơ chế swap A/B để phát hiện thiên vị vị trí.

### 1.2 Regression Testing & Release Gate (`main.py`, `engine/runner.py`)
Tôi xây dựng luồng benchmark V1 vs V2 và cơ chế ra quyết định release tự động.

- **Benchmark 2 phiên bản:** chạy độc lập `Agent_V1_Base` và `Agent_V2_Optimized` trên cùng Golden Dataset 60 cases.
- **Tự động tính delta:** so sánh `avg_score` giữa V2 và V1 để phát hiện regression.
- **Release Gate theo ngưỡng chất lượng:**
  - `GATE_MIN_SCORE = 3.5`
  - `GATE_MIN_HIT_RATE = 0.70`
  - `GATE_MIN_AGREEMENT = 0.70`
  - `GATE_MAX_REGRESSION = -0.2`
- **Quyết định tự động:** trả về `APPROVE` hoặc `BLOCK`, đồng thời liệt kê rõ `gate_reasons`.
- **Xuất báo cáo chuẩn:** ghi `reports/summary.json` và `reports/benchmark_results.json` để phục vụ chấm điểm.

---

## 2. Kết quả đạt được

Kết quả benchmark hiện tại (theo `reports/summary.json`):

| Hạng mục | Kết quả |
|---|---|
| Tổng số test cases | 60 |
| Judge models | gpt-4o-mini + gpt-4o |
| Agreement Rate (V2) | **100.0%** |
| Conflict auto-resolved cases (V2) | 0 |
| Avg Judge Score V1 | **4.217** |
| Avg Judge Score V2 | **4.325** |
| Delta (V2 - V1) | **+0.108** |
| Regression Gate | **APPROVE** |
| Lý do gate | Không có (`gate_reasons: []`) |

Ý nghĩa: hệ thống đã chạy đầy đủ V1 vs V2 và kích hoạt cơ chế gate tự động đúng thiết kế. V2 đạt toàn bộ ngưỡng chất lượng và có cải thiện so với V1 nên được approve release.

---

## 3. Giải thích kỹ thuật (Technical Depth)

### 3.1 Agreement Rate trong Multi-Judge
Agreement Rate đo mức độ nhất quán giữa 2 Judge:

```
agreement_rate = 1.0  nếu |score_A - score_B| <= 1
agreement_rate = 0.5  nếu |score_A - score_B| > 1
```

Metric này đơn giản nhưng hiệu quả để theo dõi độ ổn định của cơ chế chấm điểm trong pipeline tự động.

### 3.2 Cơ chế xử lý xung đột (Conflict Resolution)
Khi 2 Judge bất đồng mạnh (`diff > 1`), hệ thống dùng nguyên tắc bảo thủ:

```
final_score = min(score_A, score_B)
```

Thiết kế này giảm rủi ro false-positive (đánh pass quá lạc quan) trong bối cảnh release gate cần an toàn.

### 3.3 Regression Gate là gì?
Regression Gate là tầng kiểm soát chất lượng trước release:

- Kiểm tra ngưỡng tuyệt đối của bản mới (score/hit rate/agreement).
- Kiểm tra ngưỡng thay đổi so với bản cũ (`delta_score`).
- Chỉ khi đạt toàn bộ điều kiện mới `APPROVE`, ngược lại `BLOCK`.

Trong bài này, V2 được `APPROVE` vì đạt ngưỡng điểm tối thiểu, giữ chất lượng ổn định và có cải thiện điểm trung bình so với V1.

### 3.4 Position Bias trong LLM-as-a-Judge
Position bias là hiện tượng Judge thiên vị thứ tự trình bày đáp án. Hàm `check_position_bias(...)` kiểm tra bằng cách chấm cặp (A,B) và (B,A), từ đó phát hiện khả năng thiên vị để tăng độ tin cậy đánh giá.

---

## 4. Khó khăn và cách giải quyết (Problem Solving)

**Vấn đề 1: Cần cơ chế tổng hợp điểm ổn định khi nhiều Judge bất đồng**
- Nếu chỉ trung bình cộng mọi trường hợp có thể làm tăng rủi ro pass sai.
- **Giải pháp:** thêm nhánh conflict tự động (`diff > 1`) và lấy điểm thấp hơn để đảm bảo an toàn.

**Vấn đề 2: Khó chuẩn hóa output từ Judge để xử lý máy**
- Judge có thể trả text tự do gây lỗi parse.
- **Giải pháp:** bắt buộc output JSON + có fallback parse error về score mặc định.

**Vấn đề 3: Quyết định release dễ cảm tính nếu không có rule rõ ràng**
- **Giải pháp:** định nghĩa rõ các ngưỡng gate trong code (`GATE_*`) và trả về danh sách lý do block cụ thể, giúp quyết định minh bạch.

---

## 5. Nhìn lại và rút kinh nghiệm

Điều tôi học được từ phần việc của mình:

1. **Một Judge là chưa đủ cho hệ thống đánh giá production-like.** Multi-judge giúp tăng độ tin cậy và khả năng audit.
2. **Consensus cần đi kèm conflict policy rõ ràng.** Không chỉ đo agreement, mà còn phải có hành vi an toàn khi bất đồng.
3. **Regression Gate là bắt buộc trong vòng đời AI system.** Nếu không có gate, team dễ release phiên bản kém chất lượng.
4. **Số liệu phải gắn với quyết định.** Việc xuất summary + reasons giúp chuyển từ “đánh giá để xem” sang “đánh giá để ra quyết định release”.
