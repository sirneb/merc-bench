# Task B spec: TTL-LRU cache

Implement a Python module containing a single class `TTLLRUCache`, standard library only.

## Constructor

`TTLLRUCache(capacity, default_ttl=None, clock=time.monotonic)`

- `capacity`: int >= 1, max number of entries. Raise `ValueError` if < 1.
- `default_ttl`: seconds entries live by default. `None` means entries never expire unless a per-entry ttl is given.
- `clock`: zero-arg callable returning current time in seconds (injectable for testing).

## Methods

- `put(key, value, ttl=None)`: insert/update. `ttl` overrides `default_ttl` for this entry (`None` = use default). Updating an existing key updates its value, resets its expiry from now, and makes it most-recently-used. If inserting a NEW key while at capacity, evict the least-recently-used entry first (expired entries should be purged before deciding to evict a live one).
- `get(key)`: return the value and mark the entry most-recently-used. If the key is absent, raise `KeyError`. If the entry has expired (clock() >= insertion time + ttl), remove it, count it as an expiration AND a miss, and raise `KeyError`. Successful gets count as hits; absent keys count as misses.
- `__contains__(key)`: True if present and not expired. Does NOT update recency and does NOT count toward hits/misses. Expired entries encountered here are removed and counted as expirations.
- `__len__()`: number of live (non-expired) entries; purges expired entries as a side effect (purged entries count as expirations).
- `stats()`: return a dict `{"hits": int, "misses": int, "evictions": int, "expirations": int}`. Evictions = capacity-based removals only. Expirations = ttl-based removals only. Each removed entry is counted at most once (an entry removed as expired is an expiration, not an eviction).

## Notes

- Recency order: both `get` hits and `put` (new or update) make the entry most-recently-used.
- Expiry uses `clock() >= inserted_at + ttl` (entries with ttl `None` never expire).
- No background threads; expiry is lazy (checked on access/len/put-capacity decisions).
