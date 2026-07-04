from privatetv.domain.models import MediaItem, SourceKind
from privatetv.schedule import AlphabeticalStrategy, ShuffleNoRepeatStrategy


def _item(title: str, source_uri: str) -> MediaItem:
    return MediaItem(
        id=1,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=source_uri,
        source_root=None,
        title=title,
        media_type="file",
        duration_seconds=60,
    )


def test_alphabetical_strategy_orders_by_title_case_insensitive() -> None:
    items = [_item("Beta", "file:///b"), _item("alpha", "file:///a")]

    ordered = AlphabeticalStrategy().order(items)

    assert [item.title for item in ordered] == ["alpha", "Beta"]


def test_shuffle_no_repeat_returns_each_item_once_per_cycle() -> None:
    items = [_item("A", "file:///a"), _item("B", "file:///b"), _item("C", "file:///c")]

    ordered = ShuffleNoRepeatStrategy(seed=42).order(items)

    assert sorted(item.source_uri for item in ordered) == ["file:///a", "file:///b", "file:///c"]
    assert len(ordered) == 3
