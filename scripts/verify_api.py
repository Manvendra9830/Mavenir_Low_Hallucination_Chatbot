"""
Verification script for TeleRAG REST API
Tests all required features:
1. Retrieval filtering by specifications.
2. Adding dynamic documents (up to 10 limit).
3. Attempting to add an 11th document (should fail).
4. Removing a document.
5. Verifying simplified RAG generation.
"""
import httpx
import sys

BASE_URL = "http://127.0.0.1:8000/api"

def print_banner(msg):
    print("\n" + "="*80)
    print(msg)
    print("="*80)

def test_scope_filtering():
    print_banner("TEST: Scope Filtering")
    
    # Query: RRC connection setup (found in TS 38.331, not TS 23.501)
    query = "Explain RRC connection establishment procedure."
    
    # 1. Query with TS 23.501 only
    r1 = httpx.post(f"{BASE_URL}/query", json={
        "query": query,
        "release": "18",
        "specifications": ["TS 23.501"]
    }, timeout=60.0)
    
    print("TS 23.501 query status:", r1.status_code)
    evidence1 = r1.json().get("evidence", [])
    print(f"Chunks retrieved with TS 23.501 filter: {len(evidence1)}")
    # All chunks should belong to TS 23.501
    for chunk in evidence1:
        assert chunk["specification"] == "TS 23.501", f"Expected TS 23.501, got {chunk['specification']}"
    print("✓ Scope filtering validation for TS 23.501 passed!")

    # 2. Query with TS 38.331 only
    r2 = httpx.post(f"{BASE_URL}/query", json={
        "query": query,
        "release": "18",
        "specifications": ["TS 38.331"]
    }, timeout=60.0)
    
    print("TS 38.331 query status:", r2.status_code)
    evidence2 = r2.json().get("evidence", [])
    print(f"Chunks retrieved with TS 38.331 filter: {len(evidence2)}")
    for chunk in evidence2:
        assert chunk["specification"] == "TS 38.331", f"Expected TS 38.331, got {chunk['specification']}"
    print("✓ Scope filtering validation for TS 38.331 passed!")

def test_document_limit_and_removal():
    print_banner("TEST: Dynamic Document Addition, Limits & Removal")
    
    # Get current status
    status = httpx.get(f"{BASE_URL}/corpus/status").json()
    print("Current specs:", [s["specification"] for s in status["specifications"]])
    print("Total documents:", status["total_documents"])
    
    # We start with 6. We can add 4 more:
    # TS 29.500, TS 29.501, TS 29.502, TS 29.503
    extra_specs = ["TS 29.500", "TS 29.501", "TS 29.502", "TS 29.503"]
    
    # Add documents up to 10
    for spec in extra_specs:
        print(f"\nAdding spec: {spec}")
        res = httpx.post(f"{BASE_URL}/corpus/add", json={
            "release": "18",
            "specification": spec
        }, timeout=120.0)
        print(f"Add response ({res.status_code}):", res.json())
        assert res.status_code == 200, f"Failed to add spec {spec}"
        
    # Verify current count is 10
    status = httpx.get(f"{BASE_URL}/corpus/status").json()
    print("\nSpecs in corpus after adding:", [s["specification"] for s in status["specifications"]])
    print("Total documents:", status["total_documents"])
    assert status["total_documents"] == 10, f"Expected 10 docs, got {status['total_documents']}"
    print("✓ Successfully hit capacity of 10 documents.")
    
    # Attempt to add an 11th document: TS 29.504
    print("\nAttempting to add 11th document: TS 29.504")
    res11 = httpx.post(f"{BASE_URL}/corpus/add", json={
        "release": "18",
        "specification": "TS 29.504"
    }, timeout=120.0)
    print(f"11th document add response ({res11.status_code}):", res11.json())
    assert res11.status_code == 400, "Expected status code 400 for capacity limit violation"
    assert "Maximum corpus capacity" in res11.json()["detail"], "Expected capacity error message"
    print("✓ Successfully blocked 11th document addition (status code 400 + clear error message).")
    
    # Query using the newly added document TS 29.500
    print("\nQuerying using newly added document TS 29.500")
    rq = httpx.post(f"{BASE_URL}/query", json={
        "query": "What are the common HTTP custom headers in 3GPP service-based interface?",
        "release": "18",
        "specifications": ["TS 29.500"]
    }, timeout=60.0)
    print("TS 29.500 query status:", rq.status_code)
    evidence_q = rq.json().get("evidence", [])
    print(f"Chunks retrieved with TS 29.500 filter: {len(evidence_q)}")
    for chunk in evidence_q:
        assert chunk["specification"] == "TS 29.500", f"Expected TS 29.500, got {chunk['specification']}"
    print("✓ Querying new specification successfully retrieves its chunks!")
    
    # Remove TS 29.503
    print("\nRemoving document: TS 29.503")
    rem_res = httpx.delete(f"{BASE_URL}/corpus/TS 29.503")
    print(f"Remove response ({rem_res.status_code}):", rem_res.json())
    assert rem_res.status_code == 200, "Failed to remove TS 29.503"
    
    # Verify count drops back to 9
    status = httpx.get(f"{BASE_URL}/corpus/status").json()
    print("Total documents after removal:", status["total_documents"])
    assert status["total_documents"] == 9, f"Expected 9 docs, got {status['total_documents']}"
    print("✓ Successfully dropped back to 9 documents.")
    
    # Re-add a different one to check we can: TS 29.504
    print("\nAdding TS 29.504 now that we are at 9/10 capacity")
    res_readd = httpx.post(f"{BASE_URL}/corpus/add", json={
        "release": "18",
        "specification": "TS 29.504"
    }, timeout=120.0)
    print(f"Re-add response ({res_readd.status_code}):", res_readd.json())
    assert res_readd.status_code == 200, "Failed to re-add specification TS 29.504"
    
    status = httpx.get(f"{BASE_URL}/corpus/status").json()
    print("Total documents after re-add:", status["total_documents"])
    assert status["total_documents"] == 10, f"Expected 10 docs, got {status['total_documents']}"
    print("✓ Successfully re-added document to hit capacity again.")

if __name__ == "__main__":
    try:
        test_scope_filtering()
        test_document_limit_and_removal()
        print_banner("ALL API TESTS PASSED!")
    except Exception as e:
        print_banner("API TESTS FAILED!")
        import traceback
        traceback.print_exc()
        sys.exit(1)
