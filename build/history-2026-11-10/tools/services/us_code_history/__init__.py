"""US Code history: traces each change between annual editions of a US Code title to the public law that made it.

The pipeline reads the annual editions GovInfo publishes for a title, compares them provision by provision, finds
the public laws enacted in between, reads each law's own amending instructions (GovInfo's USLM markup tags the
target, the action and the quoted text), and replays those instructions on the older text. A cause is confirmed
only when the replay reproduces the newer text. Everything it publishes carries the sources, dates and
fingerprints needed to check it.

Run with ``python -m services.us_code_history.build --title 11``.
"""
