```python
splits = {
    "E1": {k: [int(x) for x in v] for k, v in split_raw["E1"].items() if isinstance(v, list) and not any(isinstance(x, str) for x in v) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)},
    "E2": {k: [int(x) for x in v] for k, v in split_raw["E2"].items() if isinstance(v, list) and not any(isinstance(x, str) for x in v) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)},
}
```
