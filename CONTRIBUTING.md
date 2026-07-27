# Contributing

Bug reports and format research are welcome, but do not upload complete save
directories, `settings.txt`, tokens, game binaries or copyrighted game assets.

For code changes:

1. Use Python 3.10 or newer.
2. Keep runtime dependencies at zero unless a dependency removes substantial,
   demonstrated risk.
3. Add focused `unittest` coverage.
4. Run `python -m unittest discover -s tests -v`.
5. Document the evidence behind new level mappings or binary fields.

Synthetic fixtures are preferred. If a bug only reproduces with a real save,
provide a redacted structural description and hashes rather than the save.
