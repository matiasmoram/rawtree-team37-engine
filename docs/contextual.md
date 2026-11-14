# Device/region priors and subcategory/brand trends

This is an isolated `ContextualPolicy` challenger based on the nocovis control's
weights. This remains a challenger; the active practice allocation is documented in cartfirst.md.

The background builder reads organic `shop.events` from the six hours strictly
before an explicit information cutoff. Purchase, cart and view intent weights are
1.0, 0.25 and 0.02, decayed with a three-hour half-life. It creates smoothed item
distributions for `(device, region)`, device, region and global traffic. Pair priors
borrow from the device/region marginals; those borrow from the global distribution.
These organic intent distributions are candidate signals, not calibrated purchase
probabilities for the recommendation carousel.

Sparse context lookup falls back in this order:

1. Pair, with at least 500 events and intent mass 10.
2. Device, with at least 200 events and intent mass 5.
3. Region, with at least 200 events and intent mass 5.
4. Global distribution.

For trends, the baseline is the seven days before the recent six-hour window,
combining history and live events with strict upper bounds. Subcategory and brand
intent **shares** are compared, rather than absolute counts: the historical and
live streams have different event throughput. Both periods need at least 100
events in a group. Sparse groups keep lift 1; supported share lifts are smoothed
and bounded to 0.5–2.0.

The policy adds at most 60 context candidates for home/no-view requests and new
users. Context and trend multipliers apply only to discovery items, preserving
known viewed items, session preferences and purchased-item penalties. Inactive
products and products added after the request are excluded. Combined contextual
effects are bounded to 0.5–2.0. No request performs SQL or filesystem IO.

Run separately from the live runner:

```powershell
.venv/Scripts/python.exe scripts/refresh_context.py --once
.venv/Scripts/python.exe scripts/refresh_context.py --every 600
```

Artifacts are atomically saved to ignored `cache/contextual.json`. Loading validates
shapes and finite signals. Historical consumers reject artifacts newer than their
request; live consumers reject artifacts older than two hours. A missing, invalid,
future or stale artifact reduces the challenger to the existing nocovis scoring.
Call `refresh_context()` from a background thread after rebuilding the artifact.

Validation must compare this challenger prospectively in the same window against
the control, focusing separately on home/no-views, platform-new users with session
views, returning users and new products. Organic popularity, a lower offline
prediction loss or faster inference does not establish improved simulator conversion.
