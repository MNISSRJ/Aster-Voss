from memory import brain

def test_memory_ids_are_unique():
    first = brain._entry_id()
    second = brain._entry_id()
    assert first != second
