# Forum Post Draft

## Legacy save migration tool for 0.1059 / 2.0.16 to 2.1.278

I have published a Python tool that directly converts legacy Turing Complete
circuits to the current v15 save format.

The important bug is that old v6 used enum value 92 for Custom, while the
current enum uses 92 for `com_time`. The current legacy loader skips the old
Custom payload, loses stream alignment, and can save a complex CPU as blank.

The tool bypasses that path and:

- keeps the source save read-only;
- prepares a separate candidate directory;
- parses v6 with the old enum and writes a complete v15 circuit;
- also converts v7, v9, v10, v13 and v14 circuits to v15;
- maps legacy component-factory definitions into the current foundry directory
  and verifies the full Custom-ID dependency closure;
- verifies component and wire counts after a full v15 reparse;
- preserves both sides of schematic name collisions;
- keeps the current `settings.txt`;
- maps only evidence-backed campaign completion states;
- avoids duplicate campaign inputs/outputs by leaving immutable scaffolding for
  the current runtime to inject and derives runtime counts from bundled campaign circuits;
- derives the old global OVERTURE architecture into the current staged levels;
- reports every approximate/placeholder component mapping;
- supports safe backup defaults or explicit no-retention options;
- detects missing circuits and count-changing rewrites after loading.

Validation so far: all 92 source circuits from 0.1059 plus six derived OVERTURE
stage circuits produce 98 verified v15 circuits. All wires are retained; 150
campaign ports are intentionally injected by the current runtime.
The derived OVERTURE stages contain 38 user components plus either 9 or 11
current immutable scaffold components, for runtime totals of 47 or 49.
One real RV64 design remained 23 components and 190 wires, including 16 Custom
instances. Its 34 foundry definitions cover all 33 referenced Custom IDs and
189 reported Custom instances after derivation with no missing or duplicate definition.

The project includes format notes, level mappings, report documentation and
tests. Please do not attach complete saves to issues because `settings.txt` may
contain a personalized token.

Repository: https://github.com/Cong0707/turing-complete-migration
