from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionDecision:
    from_class: str | None
    to_class: str
    reason: str
    age_blocks: int


class OutputClassifier:
    def __init__(self, t_min: int):
        self.t_min = t_min

    def classify_new_output(self) -> TransitionDecision:
        return TransitionDecision(from_class=None, to_class="MH", reason="output_created", age_blocks=0)

    def classify_temporal_transition(self, current_class: str, creation_height: int, current_height: int, is_spent: bool) -> TransitionDecision | None:
        age_blocks = current_height - creation_height
        if age_blocks < 0:
            raise ValueError("negative age is invalid")
        if is_spent or current_class != "MH":
            return None
        if age_blocks >= self.t_min:
            return TransitionDecision(from_class="MH", to_class="ML", reason="reached_t_min", age_blocks=age_blocks)
        return None

    def classify_spend(self, current_class: str, creation_height: int, spend_height: int) -> TransitionDecision:
        age_blocks = spend_height - creation_height
        if age_blocks < 0:
            raise ValueError("negative age is invalid")
        if current_class == "IM":
            raise ValueError("IM is terminal")
        if age_blocks == 0:
            return TransitionDecision(from_class=current_class, to_class="IM", reason="same_block_spend", age_blocks=0)
        if current_class == "MH":
            return TransitionDecision(from_class="MH", to_class="IM", reason="spent_from_mh", age_blocks=age_blocks)
        if current_class == "ML":
            return TransitionDecision(from_class="ML", to_class="IM", reason="spent_from_ml", age_blocks=age_blocks)
        raise ValueError(f"unexpected current class: {current_class}")
