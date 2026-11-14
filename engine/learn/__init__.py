"""Learned rankers trained on our own live feedback (team_NN.feedback).

- ``dataset``: one row per shown item of each answered request, features exactly as served (``engine.features``).
- ``train``: LightGBM click / purchase / factored models with a time-based split and a validation report.
- ``scoring``: model loading and scoring shared by training reports and the serving policy.
- ``live_check``: run a trained policy on recent live requests (latency, list composition).

See ``docs/live_ranker.md``.
"""
