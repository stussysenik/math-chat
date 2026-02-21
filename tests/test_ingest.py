from truthbattle.ingest import extract_latest_user_input


def test_extract_text_only():
    messages = [{"role": "user", "content": "solve x^2-1=0"}]
    text, images = extract_latest_user_input(messages)
    assert text == "solve x^2-1=0"
    assert images == []


def test_extract_multimodal_parts():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "find roots"},
                {"type": "image_url", "image_url": {"url": "https://x.test/img.png"}},
            ],
        }
    ]
    text, images = extract_latest_user_input(messages)
    assert "find roots" in text
    assert images == ["https://x.test/img.png"]


def test_extract_image_only():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "https://x.test/math.png"}}
            ],
        }
    ]
    text, images = extract_latest_user_input(messages)
    assert text == ""
    assert images == ["https://x.test/math.png"]


def test_extract_no_user_message_returns_empty():
    messages = [{"role": "assistant", "content": "tool banner text"}]
    text, images = extract_latest_user_input(messages)
    assert text == ""
    assert images == []


def test_extract_markdown_image_url():
    messages = [
        {
            "role": "user",
            "content": "how to solve this? ![img](http://127.0.0.1:3000/api/v1/files/id/content)",
        }
    ]
    text, images = extract_latest_user_input(messages)
    assert "how to solve this?" in text
    assert images == ["http://127.0.0.1:3000/api/v1/files/id/content"]


def test_extract_input_image_shape():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "solve"},
                {
                    "type": "input_image",
                    "image_url": {"url": "data:image/png;base64,abc"},
                },
            ],
        }
    ]
    text, images = extract_latest_user_input(messages)
    assert text == "solve"
    assert images == ["data:image/png;base64,abc"]
