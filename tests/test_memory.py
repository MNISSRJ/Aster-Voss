from memory import brain

def test_memory_ids_are_unique():
    first = brain._entry_id()
    second = brain._entry_id()
    assert first != second


def test_memory_retrieval_interface():
    from memory.retrieval import LexicalMemoryRetriever
    hits = LexicalMemoryRetriever().search(
        "python",
        [{"text": "Mint likes Python projects"}, {"text": "unrelated note"}],
    )
    assert hits and "Python" in hits[0].text
