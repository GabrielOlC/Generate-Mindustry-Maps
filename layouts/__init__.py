"""Layout generators, one module per map type.

Every module here that defines a subclass of cm_layout.clLayout is a map type: cm_layout.fnFindLayouts
finds it and the controller (wf_generate.py) offers it, with no other file to change. See CLAUDE.md for
the contract a layout has to meet.
"""
