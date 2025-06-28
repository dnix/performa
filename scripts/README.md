# Scripts Directory

This directory contains ad hoc scripts for testing and validation.

## Available Scripts

### `stress_test_residential.py`
Comprehensive stress testing for the residential asset module across the full spectrum of real estate users.

**Usage:**
```bash
python scripts/stress_test_residential.py
```

**What it tests:**

**Fundamental Architecture:**
- Core lease cash flow computation
- Component aggregation functionality  
- UUID field presence validation

**User Segments Covered:**
- **Small Developer**: 3-4 units (Triplex, Fourplex)
- **Small Investor**: 8 units (Mixed unit types)
- **Regional Investor**: 24 units (Multi-family complex)
- **Mid-size Operator**: 48 units (Professional management)
- **Regional Portfolio**: 96 units (Portfolio-scale property)
- **Institutional**: 150-300 units (Class A & B properties)

**Performance Benchmarking:**
- Tests 8 different property scales (3-300 units)
- Measures execution time and units/second processing speed
- Validates financial accuracy (PGR calculations)
- Generates comprehensive user experience analysis

**Expected Performance (Current Results):**
- **Small Developer**: ~1,700 units/sec (2ms response time)
- **Small-Mid Market**: ~2,900 units/sec (3-15ms response time)  
- **Institutional**: ~3,570 units/sec (28-84ms response time)

**Output Includes:**
- Fundamental sanity check validation
- Performance insights by user segment
- User experience timing breakdown
- Competitive analysis vs industry tools
- Use case enablement summary

The script validates that architectural changes don't break core functionality while demonstrating that Performa delivers **real-time performance competitive with Argus and Rockport** across all user segments. 