"""Read-only inspection of preserved review evidence, independent of execution.

Importing this package does not load the active workflow, a graph, or a model.
Use Python's ``-B`` option when the entire inspection process must avoid writing
bytecode; a package cannot prevent writes that precede its own import.
"""
