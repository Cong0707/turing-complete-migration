# Research Sources

Public references used during the initial implementation:

- [Alpha Branch](https://turingcomplete.wiki/wiki/Alpha_Branch)
- [Save breaker changes](https://turingcomplete.wiki/wiki/Save_breaker_changes)
- [Backing up your save directory](https://turingcomplete.wiki/wiki/Backing_up_your_save_directory)
- [Known issues/2.0.16](https://turingcomplete.wiki/wiki/Known_issues/2.0.16)
- [Custom level creation/circuit.data](https://turingcomplete.wiki/wiki/Custom_level_creation/circuit.data)
- [Alpha Branch/Word width](https://turingcomplete.wiki/wiki/Alpha_Branch/Word_width)
- [guzba/supersnappy](https://github.com/guzba/supersnappy) — MIT-licensed
  reference implementation confirming that the embedded library is standard
  raw Snappy. The Python decoder in this repository is independently small and
  follows the public Snappy tag format.
- [Stuffe/save_monger](https://github.com/Stuffe/save_monger) — CC0 format
  implementation. Current reference commit `d6505a8` documents v15-era fields;
  historical commit `22fa398` documents the 0.1042 Beta v6 layout and old enum.

Local evidence was collected from user-owned save copies and the installed
2.1.276 executable. No save data, tokens, game binaries, or extracted game
source are included in this repository.

The wiki warns that the alpha branch is intentionally a “save breaker”, that
switching backward can break saves, and that complete backups must not be
shared because `settings.txt` contains a personalized token. Those warnings
directly shape this project's explicit conversion, safe-default and redaction behavior.
