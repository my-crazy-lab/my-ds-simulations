#!/usr/bin/env python3
"""
Integration Test Runner

Runs all integration tests for the microservices system.
"""

import asyncio
import sys
import time
from datetime import datetime

from cross_service_saga_test import run_integration_tests as run_saga_tests
from outbox_pattern_test import run_outbox_pattern_tests
from cqrs_flow_test import run_cqrs_flow_tests

async def main():
    """Run all integration tests"""
    
    print("🚀 STARTING COMPREHENSIVE INTEGRATION TESTS")
    print("=" * 80)
    print(f"📅 Test run started at: {datetime.now().isoformat()}")
    print("=" * 80)
    
    start_time = time.time()
    test_results = {}
    
    # Test suites to run
    test_suites = [
        ("Cross-Service Saga Tests", run_saga_tests),
        ("Outbox Pattern Tests", run_outbox_pattern_tests),
        ("CQRS Flow Tests", run_cqrs_flow_tests),
    ]
    
    # Run each test suite
    for suite_name, test_function in test_suites:
        print(f"\n🧪 Running {suite_name}...")
        suite_start_time = time.time()
        
        try:
            await test_function()
            suite_duration = time.time() - suite_start_time
            test_results[suite_name] = {
                "status": "PASSED",
                "duration": suite_duration,
                "error": None
            }
            print(f"✅ {suite_name} completed in {suite_duration:.2f}s")
            
        except Exception as e:
            suite_duration = time.time() - suite_start_time
            test_results[suite_name] = {
                "status": "FAILED", 
                "duration": suite_duration,
                "error": str(e)
            }
            print(f"❌ {suite_name} failed after {suite_duration:.2f}s: {e}")
    
    # Print final results
    total_duration = time.time() - start_time
    
    print("\n" + "=" * 80)
    print("📊 INTEGRATION TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed_count = 0
    failed_count = 0
    
    for suite_name, result in test_results.items():
        status_icon = "✅" if result["status"] == "PASSED" else "❌"
        print(f"{status_icon} {suite_name}: {result['status']} ({result['duration']:.2f}s)")
        
        if result["status"] == "PASSED":
            passed_count += 1
        else:
            failed_count += 1
            if result["error"]:
                print(f"   Error: {result['error']}")
    
    print("-" * 80)
    print(f"📈 Total: {len(test_suites)} suites, {passed_count} passed, {failed_count} failed")
    print(f"⏱️  Total duration: {total_duration:.2f}s")
    print(f"📅 Test run completed at: {datetime.now().isoformat()}")
    
    if failed_count > 0:
        print("\n❌ SOME TESTS FAILED!")
        sys.exit(1)
    else:
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
