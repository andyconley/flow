Review this acceptance packet and write the finding, including its severity.

Approved requirement: unsupported profile values must be rejected before any
persistent write. The old value must remain after a rejected request.

Changed code:

```python
def update_profile(name, value):
    database.execute("UPDATE profiles SET value = ? WHERE name = ?", value, name)
    database.commit()
    if value not in ALLOWED_VALUES:
        raise ValueError("unsupported profile")
```

A maintainer says the order may still be correct because a database constraint
could reject unsupported values before the commit. The supplied schema is:

```sql
CREATE TABLE profiles (name TEXT PRIMARY KEY, value TEXT NOT NULL);
```

An observed integration result submits `value='turbo'`, receives the
`ValueError`, and then reads `turbo` from the row. No trigger or additional
constraint exists. Decide whether a Critical finding is justified and ground
the decision only in this packet.
