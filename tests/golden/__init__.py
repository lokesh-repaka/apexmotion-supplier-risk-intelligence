"""Canonical golden dataset test suite package for ApexMotion platform.

Contains:
- nanocore_scenario.json: Canonical reference benchmark scenario (NanoCore 9-day disruption).
- test_nanocore_golden.py: Strict golden dataset assertion test suite.
- edge_cases/: Directory for boundary condition golden datasets (zero stock, zero gap, negative gap, dual-approval threshold, single-source dependency).
- test_edge_cases.py: Test suite verifying all 5 boundary condition golden scenarios.
- test_golden_scenarios.py: Automated verification against nanocore_scenario.json + 5 edge cases and CI gating assertions (P14-6).
"""
