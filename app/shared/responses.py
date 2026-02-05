from typing import Any, Dict

def to_dict(row: Any) -> Dict[str, Any]:
    # Row can be RowMapping or ORM-like. For Core results, mapping works.
    if row is None:
        return {}
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    if isinstance(row, dict):
        return row
    # Fallback for SQLAlchemy Row where keys are accessible
    try:
        return {k: getattr(row, k) for k in row.keys()}  # type: ignore
    except Exception:
        return dict(row)
