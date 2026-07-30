"""Hand-computed stats — one stat (or stat concept) per file.

Layout:
    core/         shared foundations (pitch classification, PA outcomes,
                  innings math, aggregation, annotation, selectors)
    batting/      counting-stat batter formulas (AVG, OBP, ISO, BABIP, …)
    pitching/     counting-stat pitcher formulas (ERA, WHIP, K/9, …)
    discipline/   plate-discipline rates from pitch-level data
    batted_ball/  batted-ball quality metrics from pitch-level data
    advanced/     stats needing league constants or external data
                  (wOBA, wRC+/TJBat+, FIP, xWPCT).  The constants themselves
                  are fetched and cached by ``site_builder.league_constant``
                  and passed in as arguments — no module under stats/ does
                  any I/O.
    tables/       per-pitch-type table builders (compute + cross-level combine)

Adding a new stat = add one file with a pure ``compute_*`` function, then hook
it into the relevant assembler:
    - season-row derived stats  → ``core/annotate.py``
    - pitcher statcast summary  → ``pitcher_statcast.py``
    - batter statcast summary   → ``batter_statcast.py``
    - cross-level combined row  → ``combine.py``
"""
