# Archive

Historical deliverables kept for provenance. They are **not** part of the
current 3-screen story and may not run after the move.

- `presentation_public_10part.html` - the old plain-language 10-part deck
  (superseded by `reports/twin_story.html` and `reports/presentation_public.html`).
- `dashboard/dashboard.html` - the old Protein-7 console snapshot.
- `dashboard/dashboard_state.py`, `dashboard/dashboard_server.py`,
  `dashboard/make_dashboard.py`, `dashboard/dashboard_template.html` - the
  console code and template. The server was a live simulation layer; the
  current deliverable is static and has no SSE or simulation regime.
- `dashboard/state.json` - the old console snapshot state.
- `make_pitch.py` - the old 10-part deck builder.

The current technical report remains at `reports/presentation.html`. The
current 3-screen story is `reports/twin_story.html`; the same page is written to
`reports/presentation_public.html` by `src/make_twin_story.py`.
