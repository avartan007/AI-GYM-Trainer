import re
import random
from services.config.workout_config import PROMPT


class LLMCoach:
    CANDIDATE_MODELS = [
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-70b-8192",
        "llama3-8b-8192",
    ]

    def __init__(self, groq_client=None):
        self.client = groq_client
        self.history = []
        self.system_prompt = PROMPT
        self._active_model = None

    def _get_fallback_cue(self, event: str, issue: str = None) -> str:
        """Reliable rule-based fallback cues if Groq API is offline or quota exceeded."""
        if event == "workout_started":
            return random.choice([
                "Let's crush this workout! Lock in your form and give it your all!",
                "Workout activated! Stay tight, controlled, and let's get those reps in!",
                "Session started! Eyes up, core tight, let's begin!",
            ])
        elif event == "workout_completed":
            return random.choice([
                "Outstanding effort! Session complete. Be proud of the work you put in today!",
                "Workout crushed! Phenomenal work on hitting your target sets!",
            ])
        elif event == "set_completed":
            return random.choice([
                "Solid set! Take a breath, shake it out, and get ready for the next one.",
                "Set completed, great pace! Rest briefly and stay focused.",
            ])
        elif event == "no_pose_detected":
            return "Please step back into the camera frame so I can track your movement."
        elif issue:
            lower_issue = issue.lower()
            if "deep" in lower_issue or "squat" in lower_issue or "knee" in lower_issue:
                return "Sink a little deeper into that squat — push your hips down and back."
            elif "forward" in lower_issue or "lean" in lower_issue:
                return "Keep your chest high and maintain a tall, neutral spine."
            elif "sag" in lower_issue or "hips" in lower_issue:
                return "Brace your abs and keep your hips aligned with your shoulders."
            elif "elbow" in lower_issue or "swing" in lower_issue:
                return "Pin your elbows to your ribs and avoid swinging your torso."
            elif "arch" in lower_issue:
                return "Tighten your core to keep your lower back neutral and protected."
            elif "balance" in lower_issue:
                return "Step into a stable base and keep your weight centered."
            return f"Stay controlled: {issue}"
        return "Strong rhythm, keep that energy moving!"

    def _clean_response(self, text: str) -> str:
        """Strip internal thinking tokens and Markdown formatting for natural TTS speech."""
        if not text:
            return ""
        # Remove reasoning tags if any
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # Remove markdown symbols and quotes
        cleaned = re.sub(r"[*_#`\"]", "", cleaned).strip()
        # Remove prefix like "Coach: " if present
        cleaned = re.sub(r"^(Apna )?AI Coach:\s*", "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned

    def give_feedback(self, event: str, issue: str = None) -> str:
        if not self.client:
            return self._get_fallback_cue(event, issue)

        prompt = f"Event: {event}"
        if issue:
            prompt += f" Form Issue: {issue}"

        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.history[-8:],
            {"role": "user", "content": prompt}
        ]

        # Try active model first if already found working
        models_to_try = [self._active_model] if self._active_model else []
        for m in self.CANDIDATE_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        for model_name in models_to_try:
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=60,
                )
                raw_text = response.choices[0].message.content or ""
                text = self._clean_response(raw_text)
                if text:
                    self._active_model = model_name
                    self.history.append({"role": "user", "content": prompt})
                    self.history.append({"role": "assistant", "content": text})
                    return text
            except Exception:
                continue

        # If all API calls fail, gracefully fall back to built-in coaching cue
        return self._get_fallback_cue(event, issue)