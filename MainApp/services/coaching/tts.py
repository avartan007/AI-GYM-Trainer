from io import BytesIO

try:
    from gtts import gTTS
    GTT_AVAILABLE = True
except ModuleNotFoundError:
    # gTTS may be absent in some deployment environments. The coach then
    # degrades gracefully to on-screen text feedback instead of crashing.
    GTT_AVAILABLE = False
    gTTS = None


class TextToSpeech:
    def __init__(self):
        self.available = GTT_AVAILABLE

    def speak(self, text, lang="en"):
        cleaned = (text or "").strip()

        if not cleaned:
            return None

        if not GTT_AVAILABLE:
            return None

        buffer = BytesIO()

        gTTS(text=cleaned, lang=lang, timeout=10).write_to_fp(buffer)

        buffer.seek(0)

        return buffer.read()