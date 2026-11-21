from farm.bot.access import is_allowed, photo_path


def test_no_allowlist_lets_everyone_in():
    assert is_allowed(123, None)
    assert is_allowed(-1001234567890, None)


def test_allowlist_keeps_others_out():
    allowed = frozenset({123, -100})
    assert is_allowed(123, allowed) and is_allowed(-100, allowed)
    assert not is_allowed(124, allowed)
    assert not is_allowed(None, allowed)
    assert not is_allowed(None, None)


def test_photo_path_inside_data_folder(tmp_path):
    (tmp_path / "scans").mkdir()
    crop = tmp_path / "scans" / "a-2.jpg"
    crop.write_bytes(b"\xff\xd8")
    assert photo_path(tmp_path, "scans/a-2.jpg") == crop.resolve()
    assert photo_path(tmp_path, "scans/A-2.JPG".lower()) == crop.resolve()


def test_photo_path_refuses_files_outside_or_not_images(tmp_path):
    data = tmp_path / "data"
    (data / "scans").mkdir(parents=True)
    secret = tmp_path / "secret.jpg"
    secret.write_bytes(b"x")
    (data / "notes.txt").write_text("x")
    assert photo_path(data, "../secret.jpg") is None
    assert photo_path(data, str(secret)) is None  # absolute path
    assert photo_path(data, "notes.txt") is None
    assert photo_path(data, "scans/missing.jpg") is None
    assert photo_path(data, "") is None
    assert photo_path(data, None) is None
    assert photo_path(data, "scans") is None
