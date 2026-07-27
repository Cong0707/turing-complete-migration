# Forum Post Draft

## Legacy save migration tool for 0.1059 / 2.0.16 to 2.1.276

I have published a Python tool that directly converts legacy Turing Complete
circuits to the current v15 save format.

The important bug is that old v6 used enum value 92 for Custom, while the
current enum uses 92 for `com_time`. The current legacy loader skips the old
Custom payload, loses stream alignment, and can save a complex CPU as blank.

The tool bypasses that path and:

- keeps the source save read-only;
- prepares a separate candidate directory;
- parses v6 with the old enum and writes a complete v15 circuit;
- also converts v7, v9 and v10 saves to v15;
- maps legacy component-factory definitions into the current foundry directory
  and verifies the full Custom-ID dependency closure;
- verifies component and wire counts after a full v15 reparse;
- preserves both sides of schematic name collisions;
- keeps the current `settings.txt`;
- maps only evidence-backed campaign completion states;
- reports every approximate/placeholder component mapping;
- supports safe backup defaults or explicit no-retention options;
- detects missing circuits and count-changing rewrites after loading.

Validation so far: 92/92 circuits from 0.1059 and 231/231 mixed v6/v7/v9/v10
circuits from 2.0.16 converted with per-file component/wire counts preserved.
One real RV64 design remained 23 components and 190 wires, including 16 Custom
instances. Its 34 foundry definitions cover all 33 referenced Custom IDs and
135 Custom instances with no missing or duplicate definition.

The project includes format notes, level mappings, report documentation and
tests. Please do not attach complete saves to issues because `settings.txt` may
contain a personalized token.

Repository: https://github.com/Cong0707/turing-complete-migration
