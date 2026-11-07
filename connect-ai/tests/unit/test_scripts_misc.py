from app.server.adapters.llm_fake import FakeLlm
from app.server.config import read_dotenv
from scripts import export_messages as em


def test_export_messages_renders_every_language():
    text = em.render(FakeLlm())
    for needle in (
        "## Finnish (fi)",
        "## Swedish (sv)",
        "## Norwegian (nb)",
        "## English (en)",
        "Julafton",
        "Julaften",
        "Jouluaatto",
        "connect_hours_suggestion",
        "Follow-up – applied",
        "Follow-up – stopped",
        "Reply STOP",
        "Vastatkaa STOP",
        "Svara STOPP",
    ):
        assert needle in text, needle
    assert text.count("### Follow-up – declined") == 4 and "{" not in text.replace("{{", "")  # no unfilled placeholders


def test_read_dotenv(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# c\nA=1\nexport B=\"two words\"\nC='x'\n\nBAD LINE\nD=a=b\n")
    assert read_dotenv(p) == {"A": "1", "B": "two words", "C": "x", "D": "a=b"}
    assert read_dotenv(tmp_path / "missing") == {}
