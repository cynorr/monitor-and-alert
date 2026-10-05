"""Existing scan metrics and candidate selection, independent of storage."""

def apply_filter(scan, config):
    scan["adr_pass"] = scan["adr20"] >= config.adr20_min_pct
    scan["adv_pass"] = scan["adv20"] >= config.adv20_min_usd

    scan["eligible"] = (scan["adr_pass"] & scan["adv_pass"] & scan["etf_pass"]
                        & scan["history_pass"])

    return scan


def add_rank(scan):
    for name in ["rfl1m", "rfl3m", "rfl6m"]:
        scan.loc[scan["eligible"], f"{name}_rank"] = scan.loc[
            scan["eligible"], name
        ].rank(method="first", ascending=False)

    for name in ["rfl1m_rank", "rfl3m_rank", "rfl6m_rank"]:
        scan[name] = scan[name].astype("Int64")

    return scan


def mark_candidate(scan, config):
    scan["candidate"] = (
        scan[["rfl1m_rank", "rfl3m_rank", "rfl6m_rank"]].le(config.rfl_top_n).any(axis=1)
    )

    return scan
