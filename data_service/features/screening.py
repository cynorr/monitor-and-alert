"""Existing scan metrics and candidate selection, independent of storage."""

ADR20_MIN = 5.0
ADV20_MIN = 5_000_000
PRICE_MIN = 5.0
TOP_N = 50

def apply_filter(scan):
    scan["price_pass"] = scan["close"] >= PRICE_MIN
    scan["adr_pass"] = scan["adr20"] >= ADR20_MIN
    scan["adv_pass"] = scan["adv20"] >= ADV20_MIN

    scan["eligible"] = scan["price_pass"] & scan["adr_pass"] & scan["adv_pass"]

    return scan


def add_rank(scan):
    for name in ["rfl1m", "rfl3m", "rfl6m"]:
        scan.loc[scan["eligible"], f"{name}_rank"] = scan.loc[
            scan["eligible"], name
        ].rank(method="first", ascending=False)

    for name in ["rfl1m_rank", "rfl3m_rank", "rfl6m_rank"]:
        scan[name] = scan[name].astype("Int64")

    return scan


def mark_candidate(scan):
    scan["candidate"] = (
        scan[["rfl1m_rank", "rfl3m_rank", "rfl6m_rank"]].le(TOP_N).any(axis=1)
    )

    return scan
