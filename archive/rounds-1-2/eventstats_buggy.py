"""eventstats: summary statistics over numeric event streams.

Spec (authoritative — behavior must match exactly):

- mean(xs): arithmetic mean of xs; returns 0.0 for empty input.
- median(xs): standard median; for even length, the average of the two
  middle values; raises ValueError for empty input.
- sample_variance(xs): unbiased sample variance (divisor n-1);
  returns 0.0 when fewer than 2 values.
- normalize(xs): min-max scaling to [0, 1]: (x - min) / (max - min).
  If all values are equal, returns a list of 0.5 of the same length.
  Returns [] for empty input.
- rolling_max(xs, w): list out where out[i] = max(xs[max(0, i-w+1) : i+1]).
  Requires w >= 1 (raises ValueError otherwise).
- top_k(xs, k): the k largest values, in descending order.
- merge_intervals(ivs): merges overlapping or touching [start, end]
  intervals. Input may be in any order. Returns merged intervals sorted
  by start.
- ewma(xs, alpha): exponentially weighted moving average.
  s[0] = xs[0]; s[i] = alpha * xs[i] + (1 - alpha) * s[i-1].
  Returns [] for empty input. Requires 0 < alpha <= 1.
- count_above(xs, t): number of values strictly greater than t.
- argmax(xs): index of the first maximum value; raises ValueError for
  empty input.
"""


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    if not xs:
        raise ValueError("median of empty sequence")
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2 == 1:
        return ys[mid]
    return (ys[mid] + ys[mid + 1]) / 2


def sample_variance(xs):
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def normalize(xs):
    if not xs:
        return []
    lo = min(xs)
    hi = max(xs)
    return [(x - lo) / hi for x in xs]


def rolling_max(xs, w):
    if w < 1:
        raise ValueError("window must be >= 1")
    out = []
    for i in range(len(xs)):
        window = xs[max(0, i - w): i + 1]
        out.append(max(window))
    return out


def top_k(xs, k):
    return sorted(xs)[:k]


def merge_intervals(ivs):
    if not ivs:
        return []
    merged = [list(ivs[0])]
    for start, end in ivs[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged


def ewma(xs, alpha):
    if not xs:
        return []
    if not (0 < alpha <= 1):
        raise ValueError("alpha must be in (0, 1]")
    out = [xs[0]]
    s = xs[0]
    for x in xs[1:]:
        s = alpha * x + (1 - alpha) * x
        out.append(s)
    return out


def count_above(xs, t):
    return sum(1 for x in xs if x > t)


def argmax(xs):
    if not xs:
        raise ValueError("argmax of empty sequence")
    best = 0
    for i in range(1, len(xs)):
        if xs[i] > xs[best]:
            best = i
    return best
