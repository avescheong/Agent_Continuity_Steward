# Scenario 01: Multi-Turn Architecture Discussion

## Fragment 1
Human:
We need to design the persistence and transaction boundary for SCS-HUD offline event vault.
Current in-memory list risks data loss if the host crashes.

AI:
I evaluated two persistence backends:
Option A: SQLite with Write-Ahead Logging (WAL) mode.
Option B: Flat JSON files with append-only logs.
I recommend SQLite with WAL mode because it provides atomic ACID transactions with minimal memory overhead.

## Fragment 2
Human:
Let's use SQLite with WAL mode because we need atomic ACID commits.
Constraint: Database file size must strictly remain under 50MB.

AI:
Understood. I will configure pragmas for synchronous=NORMAL and journal_mode=WAL in src/scs_core/db/vault.py.
Should we also compress historical snapshots with zstandard?

## Fragment 3
Human:
Checklist for this sprint:
- [ ] Implement schema migrations in src/scs_core/db/schema.sql
- [ ] Add WAL pragma config to vault.py
- [x] Initial write benchmark verified (15,000 ops/sec)

AI:
All items noted. The benchmark shows zero disk thrashing.
