"""NFR compliance validation suite.

This package consolidates all Non-Functional Requirement tests into a unified
compliance suite that can be run as a single test target.

NFRs validated:
- NFR-001: Metadata retrieval performance (<30s for 1000 tables)
- NFR-002: Sample data performance (<10s for all table sizes)
- NFR-003: Documentation output size (<1MB for 500 tables)
- NFR-004: Read-only enforcement by default
- NFR-005: Credentials never logged
"""
