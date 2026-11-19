from dgbot.api.ratelimit import RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_minute_and_day_windows() -> None:
    clock = Clock()
    limiter = RateLimiter(per_minute=2, per_day=3, clock=clock)

    assert limiter.check("a")[0] and limiter.check("a")[0]
    allowed, retry = limiter.check("a")
    assert not allowed and 0 < retry <= 61

    clock.now = 61  # new minute
    assert limiter.check("a")[0]
    clock.now = 130
    allowed, retry = limiter.check("a")  # 3 used today
    assert not allowed and retry > 3600


def test_zero_disables_a_limit() -> None:
    limiter = RateLimiter(per_minute=0, per_day=0)
    assert all(limiter.check("a")[0] for _ in range(100))
