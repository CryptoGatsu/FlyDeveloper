from fly.mind import ask_with_room


class R:
    def __init__(self, stop): self.stop_reason = stop


def test_truncated_answers_are_retried_with_more_room():
    seen = []

    def call(n):
        seen.append(n)
        if len(seen) == 1:
            raise ValueError("1 validation error for Playbook\n  Invalid JSON: EOF while parsing a string [type=json_invalid]")
        if len(seen) == 2:
            return R("max_tokens")
        return R("end_turn")

    assert ask_with_room(call, 1500).stop_reason == "end_turn"
    assert seen == [1500, 4500, 13500]


def test_other_errors_are_not_retried():
    calls = []

    def call(n):
        calls.append(n)
        raise RuntimeError("credit balance is too low")

    try:
        ask_with_room(call, 1000)
    except RuntimeError:
        pass
    assert calls == [1000]
