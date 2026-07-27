# Security and Privacy

`settings.txt` may contain a personalized server or account token. A complete
save backup must therefore be treated as private data.

The tool follows these rules:

- It never prints setting values; passive inspection reports key names only.
- It keeps the target `settings.txt` and never merges source setting values.
- By default a prepared output contains a private `archive/source/` copy for
  recovery. `--no-archive` disables it. Never attach an archive that does exist
  to GitHub issues or forum posts.
- Public bug reports should include `migration-report.json` only after checking
  paths for unwanted personal information. Do not include the save directory.
- The installed marker contains relative schematic names and hashes, but no
  setting values. Schematic names can still be personal and should be reviewed.
- Source, target and output trees may not overlap and link/junction entries are
  rejected before copying.

To report a vulnerability in the tool, open a minimal issue without uploading
real saves or tokens.
