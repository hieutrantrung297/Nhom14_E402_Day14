import json
import os

def validate_lab():
    print("[CHECK] Validating submission format...")

    required_files = [
        "reports/summary.json",
        "reports/benchmark_results.json",
        "analysis/failure_analysis.md"
    ]

    # 1. Check required files exist
    missing = []
    for f in required_files:
        if os.path.exists(f):
            print(f"[OK]   Found: {f}")
        else:
            print(f"[FAIL] Missing: {f}")
            missing.append(f)

    if missing:
        print(f"\n[FAIL] Missing {len(missing)} file(s). Please add before submitting.")
        return

    # 2. Validate summary.json content
    try:
        with open("reports/summary.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[FAIL] reports/summary.json is not valid JSON: {e}")
        return

    if "metrics" not in data or "metadata" not in data:
        print("[FAIL] summary.json missing 'metrics' or 'metadata' field.")
        return

    metrics = data["metrics"]

    print(f"\n--- Quick Stats ---")
    print(f"Total cases  : {data['metadata'].get('total', 'N/A')}")
    print(f"Avg score    : {metrics.get('avg_score', 0):.2f}")

    # EXPERT CHECKS
    has_retrieval = "hit_rate" in metrics
    if has_retrieval:
        print(f"[OK]   Retrieval Metrics found (Hit Rate: {metrics['hit_rate']*100:.1f}%)")
    else:
        print(f"[WARN] Missing Retrieval Metrics (hit_rate).")

    has_multi_judge = "agreement_rate" in metrics
    if has_multi_judge:
        print(f"[OK]   Multi-Judge Metrics found (Agreement Rate: {metrics['agreement_rate']*100:.1f}%)")
    else:
        print(f"[WARN] Missing Multi-Judge Metrics (agreement_rate).")

    if data["metadata"].get("version"):
        print(f"[OK]   Agent version info found (Regression Mode)")

    print("\n[DONE] Lab is ready for grading!")

if __name__ == "__main__":
    validate_lab()
