import urllib.request, json, time, sys

results = []

# Test 1: Health
try:
    r = urllib.request.urlopen("http://localhost:8000/api/health", timeout=5)
    d = json.loads(r.read())
    ok = d.get("status") == "ok"
    results.append(("GET /api/health", ok, str(d)))
except Exception as e:
    results.append(("GET /api/health", False, str(e)))

# Test 2: Documents
try:
    r = urllib.request.urlopen("http://localhost:8000/api/documents", timeout=5)
    d = json.loads(r.read())
    ok = "documents" in d
    doc_count = len(d.get("documents", []))
    results.append(("GET /api/documents", ok, str(doc_count) + " docs"))
except Exception as e:
    results.append(("GET /api/documents", False, str(e)))

# Test 3: Stats
try:
    r = urllib.request.urlopen("http://localhost:8000/api/stats", timeout=5)
    d = json.loads(r.read())
    ok = "total_documents" in d and "total_chunks" in d
    results.append(("GET /api/stats", ok, "docs=" + str(d["total_documents"]) + " chunks=" + str(d["total_chunks"])))
except Exception as e:
    results.append(("GET /api/stats", False, str(e)))

# Test 4: Chat - should work with uploaded docs
try:
    data = json.dumps({"question": "What is mentioned in the uploaded documents?", "history": []}).encode()
    req = urllib.request.Request("http://localhost:8000/api/chat", data=data, headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=120)
    d = json.loads(r.read())
    has_answer = bool(d.get("answer"))
    has_debug = bool(d.get("debug_info"))
    evidence = d.get("debug_info", {}).get("evidence_decision", "N/A")
    cit_count = len(d.get("citations", []))
    answer_preview = d.get("answer", "")[:100]
    results.append(("POST /api/chat (RAG)", has_answer and has_debug, "evidence=" + evidence + " citations=" + str(cit_count)))
    print("  Answer preview: " + answer_preview + "...")
except Exception as e:
    results.append(("POST /api/chat (RAG)", False, str(e)))

# Small pause to avoid rate limit
time.sleep(2)

# Test 5: Chat refusal
try:
    data = json.dumps({"question": "What is the recipe for chocolate cake?", "history": []}).encode()
    req = urllib.request.Request("http://localhost:8000/api/chat", data=data, headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=120)
    d = json.loads(r.read())
    is_refusal = "cannot answer" in d.get("answer", "").lower()
    evidence = d.get("debug_info", {}).get("evidence_decision", "N/A")
    results.append(("POST /api/chat (refusal)", is_refusal, "evidence=" + evidence + " refused=" + str(is_refusal)))
except Exception as e:
    results.append(("POST /api/chat (refusal)", False, str(e)))

# Test 6: Frontend proxy
try:
    r = urllib.request.urlopen("http://localhost:5173/", timeout=5)
    html = r.read().decode()
    ok = "root" in html
    results.append(("GET localhost:5173 (frontend)", ok, str(len(html)) + " bytes HTML"))
except Exception as e:
    results.append(("GET localhost:5173", False, str(e)))

# Print results
print()
print("=" * 72)
print("  PRODUCTION READINESS CHECK - 2AM GEEK")
print("=" * 72)
passed = 0
for name, ok, detail in results:
    status = "PASS" if ok else "FAIL"
    icon = "+" if ok else "X"
    print("  [" + icon + "] " + status.ljust(5) + "  " + name.ljust(42) + detail)
    if ok:
        passed += 1
print("=" * 72)
total = len(results)
if passed == total:
    print("  ALL " + str(total) + " CHECKS PASSED - READY FOR PRODUCTION!")
else:
    print("  " + str(passed) + "/" + str(total) + " checks passed - ISSUES FOUND")
print("=" * 72)
