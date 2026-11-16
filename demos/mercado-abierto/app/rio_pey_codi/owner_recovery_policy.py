"""RÍO owner recovery eligibility; pure and deterministic.

Authority itself is NOT established here: only AccountService.can_invite()
with an authenticated pinned-owner session grants permission to request resets.
"""

def eligible_later_account(owner, target):
    """Deny unless distinct target was registered strictly after pinned owner."""
    if owner is None or target is None:
        return False
    owner_id = getattr(owner, "id", None)
    target_id = getattr(target, "id", None)
    owner_time = getattr(owner, "created_at", None)
    target_time = getattr(target, "created_at", None)
    return (
        isinstance(owner_id, str)
        and bool(owner_id)
        and isinstance(target_id, str)
        and bool(target_id)
        and owner_id != target_id
        and type(owner_time) is int
        and type(target_time) is int
        and target_time > owner_time
    )
