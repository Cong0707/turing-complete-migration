# Changelog

## Unreleased

- Add a freestanding C to RV64I `U32` `.assembly` toolchain with startup code,
  a code-only linker layout, opcode/funct validation and reproducible ELF/bin/
  objdump/map artifacts.
- Reject `.rodata`, `.data` and `.bss` instead of silently producing an invalid
  image for the user's separate instruction/data memory architecture.
- Add 11 regression tests for the compiler wrapper without requiring a local
  RISC-V toolchain.
- Add a standalone little-endian RV64I `spec.isa` covering the 12 opcode groups
  implemented by the migrated CPU, plus a smoke-test program and Chinese
  coverage/endianness documentation.
- Validate the specification with the Turing Complete 2.1.277-synchronized
  `Stuffe/isa_spec` parser and nine upstream RV64I machine-code suites.
- Add two regression tests for the exact opcode set and 32-bit-only output rule;
  the complete suite now contains 35 tests.

## 0.2.3 - 2026-07-27

- Parse v13 and v14 current-enum circuits, including their single-string,
  immutable, cost, linked-component, selected-program, Custom and wire fields.
- Read each current campaign base circuit and count the complete immutable
  runtime scaffold instead of assuming that every level injects only ports.
- Record optional runtime component and wire counts and accept either prepared
  or runtime-written structure during postflight verification.
- Correct derived OVERTURE runtime totals to 47 components for stages 1-3 and
  49 for stages 4-5 and `binary_programming`.
- Regenerate the real 0.1059 migration as 98 verified v15 circuits with no
  retained backup; expand the generated-fixture suite to 33 tests.

## 0.2.2 - 2026-07-27

- Omit legacy level-input/output components from current campaign overlays so
  the 2.1.278 runtime can inject its immutable campaign ports exactly once.
- Keep the same interfaces in standalone `architecture/` circuits used by the
  sandbox; wires are retained in both cases.
- Record both prepared and runtime component counts, and accept the documented
  runtime-injected count during postflight verification.
- Derive the legacy global OVERTURE architecture into the five current
  Overture-building stages and `binary_programming`, while preserving the
  standalone OVERTURE schematic.
- Preserve architecture selections for current `kind = architecture` levels
  and synthesize the missing `overture_2_alu` progress row.
- Regenerate the real 0.1059 migration as 98 verified v15 circuits with no
  retained backup; expand the generated-fixture suite to 32 tests.

## 0.2.1 - 2026-07-27

- Map legacy `schematics/component_factory/` definitions to the current
  `schematics/foundry/` directory used by the 2.1.x runtime.
- Audit the Custom dependency closure: every referenced Custom ID must have one
  unique foundry definition before preparation can succeed.
- Record foundry definition counts, reference counts, missing/duplicate IDs and
  zero-design definitions in the migration report.
- Document that the current runtime reloads foundry prototypes and rebuilds the
  512-byte design from component layout via `update_custom_design`.
- Add `--steam-cloud-disabled` so a user can explicitly confirm that Steam Cloud
  is disabled while Steam itself remains running.
- Add regression tests for foundry mapping, Custom closure and the explicit
  Steam Cloud confirmation path; the suite now contains 26 tests.

## 0.2.0 - 2026-07-27

- Parse the actual legacy v6 component enum instead of handing v6 bytes to the
  current game's incompatible loader.
- Convert v6, v7, v9 and v10 circuits directly to complete v15 containers.
- Preserve component and wire counts, custom IDs, program selections, linked
  components and supported per-component settings.
- Add an independent raw-Snappy literal encoder; no third-party dependency is
  required.
- Validate every imported circuit by fully parsing v15 and comparing component
  and wire counts against the conversion report.
- Support preparing and installing when the current save directory does not yet
  exist.
- Add `--no-archive`, `--no-preserve-original`, `--no-circuit-backups` and
  `--no-backup` for users who explicitly do not want retained copies.
- Report unavoidable semantic approximations, including legacy components with
  no exact current equivalent and disconnected/teleport wire placeholders.
- Validate all 92 main circuits from a real 0.1059 save and all 231 main
  circuits from a mixed v6/v7/v9/v10 2.0.16 save without count loss.
- Expand the automated suite to 24 tests with generated valid binary fixtures.

## 0.1.0 - 2026-07-27

- Detect 0.x, 2.0.x and 2.1+ save-root layouts.
- Inspect SQLite integrity and versioned Snappy schematic containers.
- Prepare a migration without modifying source or target directories.
- Preserve conflicting schematics under collision-safe names.
- Keep an immutable `_tcm_original_circuit.data` beside every imported circuit.
- Convert compatible legacy completion rows to current `levels.txt` syntax.
- Preserve current settings and never merge source token values.
- Install with an automatic timestamped backup and support rollback.
- Detect probable game-side blank-circuit rewrites after the first load.
- Distinguish the alpha six-column and current four-column `levels.txt` formats.
- Reject nested source/target/output trees, links, junctions and invalid game paths.
- Persist imported-unit hashes in the installed marker so deleted or tampered
  preservation files are detected.
- Verify prepared saves before installation and clean failed rollback temporaries.
- Refuse install/rollback while Steam is running against an Auto-Cloud save.
