"""Audio routing layer (Deliverable 3).

Two halves:

* ``mic`` - consent-gated microphone capture with a software mirror of the
  hardware kill switch, plus a local speech-to-text backend.
* ``router`` - PipeWire helpers that duck the game audio while Bun Bun speaks
  and report the microphone's muted state.

House rules, unchanged from the persona:

* the microphone is **off by default** and never runs hot;
* capture needs an explicit listening window (push-to-talk), every time;
* a muted or missing source always wins - the kill switch outranks the agent;
* nothing ever leaves the machine (``127.0.0.1`` or local files only).
"""
