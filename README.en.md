# Turing Complete Save Migration

Python toolkit for migrating Turing Complete 0.1059 or 2.0.16 saves to the
current 2.1.x format.

Unlike the game's broken legacy path, this tool does not hand old v6 bytes to
the current loader. It parses the old component enum explicitly and writes a
complete v15 circuit, then parses that v15 output again and checks component
and wire counts.

## Features

- Reads circuit versions 6, 7, 9, 10 and 15; always produces v15.
- Preserves component/wire counts, IDs, widths, custom-component references,
  selected programs, linked components and supported settings. Campaign ports
  are intentionally left for the current runtime to inject once.
- Maps legacy `schematics/component_factory/` definitions to the current
  `schematics/foundry/` index and validates the complete Custom-ID closure.
- Migrates evidence-backed campaign completion state from 0.x SQLite or the
  2.0.x six-column `levels.txt` format.
- Derives the legacy global OVERTURE architecture into the five current
  Overture-building stages and `binary_programming`.
- Works with an existing current save or a current save path that does not yet
  exist.
- Keeps the source save read-only.
- Uses safe archive/backup defaults, with explicit no-retention switches.
- Has no third-party runtime dependencies and supports Python 3.10+.

## Root cause

Legacy v6 used component enum value `92` for `Custom`. In the current enum,
`92` means `com_time`. The current v6 loader therefore skips the old Custom
payload (`custom_id` and displacement), misaligns the rest of the stream, and
can rewrite a complex CPU as a blank circuit.

This project bypasses that path with an explicit v6-to-v15 conversion.

Current campaign levels also merge immutable ports from their bundled
`campaign/<level>/circuit.data`. Migrating the legacy copies as well creates
duplicate inputs/outputs and can make the test compiler fail on a missing
`Output._is_z`. The tool omits those legacy ports only in campaign overlays,
keeps their wires, and retains the ports in standalone sandbox architectures.

## Install

```powershell
git clone git@github.com:Cong0707/turing-complete-migration.git
cd turing-complete-migration
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
tcmigrate
```

Running `tcmigrate` without arguments opens the Chinese interactive menu.

## Commands

```powershell
tcmigrate inspect "C:\path\to\save"
tcmigrate prepare "C:\old" "C:\current" "D:\migration-output" --game-dir "D:\Game\Turing Complete"
tcmigrate verify "D:\migration-output\save"
tcmigrate install "D:\migration-output\save" "%APPDATA%\Turing Complete" --yes
tcmigrate postflight "%APPDATA%\Turing Complete"
```

To retain no generated source archive, legacy circuit copies, circuit history,
or target backup:

```powershell
tcmigrate prepare "C:\old" "C:\current" "D:\migration-output" `
  --game-dir "D:\Game\Turing Complete" `
  --no-archive --no-preserve-original --no-circuit-backups
tcmigrate install "D:\migration-output\save" "C:\current" --yes --no-backup
```

The source directory is still never modified. The no-retention switches remove
recovery options and should only be used deliberately.

## Validation

- 0.1059: all 92 source circuits converted, plus six OVERTURE-derived current
  campaign schematics, producing 98 verified v15 circuits. 150 campaign ports
  are intentionally runtime-injected; all wires are retained.
- 2.0.16: 231/231 mixed v6/v7/v9/v10 circuits, 2,125 components and 5,941 wires
  converted with per-file counts preserved.
- A real RV64 design remained 23 components and 190 wires, including 16 Custom
  instances.
- 34 foundry definitions cover all 33 referenced Custom IDs and 189 reported
  instances after OVERTURE derivation,
  with no missing or duplicate definitions.
- The repository has 32 generated-fixture tests and contains no real save data.

## Limitations

Some removed or redesigned components only have approximate current
equivalents. This is reported per conversion. Version 15 cannot represent the
old disconnected/teleport-wire endpoint, so such wires become a one-cell east
placeholder and are counted in the report. Geometry, pins, memory timing,
program keys and opcodes may still require manual repair. Equal counts prove
that a circuit was not blanked; they do not prove behavioral equivalence.

Legacy formats before v13 do not store the current 512-byte Custom design. The
tool writes an empty design; the current runtime reloads each foundry prototype
and rebuilds it from the component layout through `update_custom_design`.

Never upload a complete save: `settings.txt` may contain a personalized token.
The Chinese README and `docs/` contain the full format notes and test evidence.

Code is MIT licensed. Format research references the CC0 `Stuffe/save_monger`
project and its MIT-licensed SuperSnappy dependency. This is an independent
community tool and contains no game files or user saves.
