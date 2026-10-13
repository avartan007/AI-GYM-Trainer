import os
import sys
import time
from pathlib import Path
import platform

# Ensure MainApp directory and repository root are on sys.path
MAIN_APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = MAIN_APP_DIR.parent
if str(MAIN_APP_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_APP_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(1, str(REPO_ROOT))

# Load environment variables (.env in MainApp or repo root)
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        """Allow the app to run when an optional local .env loader is absent."""
        return False
env_file = MAIN_APP_DIR / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()

import streamlit as st
import pandas as pd
from services.auth.login_wall import render_login_wall
from services.state.session_defaults import initial_session_defaults
from services.config.workout_config import EXERCISE_OPTIONS
from services.ui.style_loader import load_css, inject_local_font, inject_webrtc_styles
from services.persistence.exercise_repository import init_db, get_users_exercises, add_exercise
try:
    from streamlit_webrtc import webrtc_streamer, WebRtcMode
except Exception:
    webrtc_streamer = None
    WebRtcMode = None

from services.tracking.metrics import sync_metrics_update
from groq import Groq
from services.coaching.llm import LLMCoach
from services.coaching.tts import TextToSpeech
from services.coaching.voice_pipeline import VoicePipeline, autoplay_audio

import platform

# Camera support - can be overridden via env var, defaults to True for localhost/deployment
cam_env = os.environ.get("CAMERA_ENABLED", "").lower()
if cam_env in ("1", "true", "yes", "on"):
    CAMERA_RUNTIME_SUPPORTED = True
elif cam_env in ("0", "false", "no", "off"):
    CAMERA_RUNTIME_SUPPORTED = False
else:
    # Default: enable camera support (works on localhost and Streamlit Cloud/Linux)
    CAMERA_RUNTIME_SUPPORTED = True

  
def main():
    st.set_page_config(
        page_icon="🏋️‍♀️",
        page_title="AI Real-time GYM Coach",
        initial_sidebar_state="expanded",
        layout="centered"
    )

    # Dynamic asset path resolution
    css_path = MAIN_APP_DIR / "static" / "style.css"
    font_path = MAIN_APP_DIR / "static" / "AdobeClean.otf"
    if css_path.exists():
        load_css(str(css_path))
    if font_path.exists():
        inject_local_font(str(font_path), "AdobeClean")

    init_db()

    if not render_login_wall():
        return 

    initial_session_defaults()

    if "voice_pipeline" not in st.session_state:
        try:
            api_key = os.environ.get("GROQ_API_KEY", "").strip()

            if not api_key and hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
                api_key = str(st.secrets["GROQ_API_KEY"]).strip()
            
            groq_client = None
            if api_key:
                groq_client = Groq(api_key=api_key, timeout=10.0)
                st.session_state.coach_mode = "Groq LLaMA/Qwen AI"
            else:
                st.session_state.coach_mode = "Built-in Coach"

            llm_coach = LLMCoach(groq_client)
            tts = TextToSpeech()
            st.session_state.voice_pipeline = VoicePipeline(llm_coach, tts)
        except Exception as e:
            # Fall back gracefully so voice pipeline never breaks completely
            llm_coach = LLMCoach(None)
            tts = TextToSpeech()
            st.session_state.voice_pipeline = VoicePipeline(llm_coach, tts)
            st.session_state.coach_mode = "Built-in Coach"

    workout_started = st.session_state.get("workout_started", False)
    
    with st.sidebar:
        st.title("🏋️‍♂️ Apna AI Coach")

        if st.session_state.get("username"):
            st.caption(f"👤 Logged in as **{st.session_state['username']}**")

        coach_status = st.session_state.get("coach_mode", "Active")
        st.caption(f"🎙️ Voice Coach: `{coach_status}`")

        st.divider()

        st.subheader("Workout Plan")

        if not workout_started:
            plan_exercise = st.selectbox("Exercise", options=EXERCISE_OPTIONS, key="plan_exercise")

            plan_sets = st.number_input("Sets", min_value=1, max_value=50, key="plan_sets", step=1)

            plan_reps = st.number_input("Reps per Set", min_value=1, max_value=50, key="plan_reps", step=1)

            st.markdown("")

            start_session_button = st.button("Start Workout", key="start_session_button")

            if start_session_button:
                st.session_state.exercise_type = plan_exercise
                st.session_state.target_sets = int(plan_sets)
                st.session_state.reps_per_set = int(plan_reps)
                st.session_state.reps = 0
                st.session_state.current_set_reps = 0
                st.session_state.sets_completed = 0
                st.session_state.workout_started = True
                st.session_state.set_cycle_started_at = time.time()
                st.session_state.last_saved_sets_completed = 0
                st.session_state.workout_completed = False
                st.session_state.rest_started_at = 0.0
                st.session_state.next_set_announced = False

                if st.session_state.voice_pipeline:
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_started",
                        exercise=plan_exercise,
                        metrics={}
                    )
                    
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result

                st.session_state.last_notified_sets_completed = 0
                st.session_state.last_notified_workout_complete = False
                st.rerun()
        else:
            exercise = st.session_state.get("exercise_type")
            sets = st.session_state.get("target_sets")
            reps = st.session_state.get("reps_per_set")

            st.info(f"**{exercise}** -- {sets} Sets / {reps} Reps")

            end_session_button = st.button("End Workout", key="end_session_button")

            if end_session_button:
                st.session_state.workout_started = False
                current_reps = st.session_state.get("current_set_reps", 0)
                user_id = st.session_state.get("user_id", 0)
                
                # If user did partial reps in their final set, preserve them in database
                if current_reps > 0 and user_id:
                    now_ts = time.time()
                    started_at = st.session_state.get("set_cycle_started_at", now_ts)
                    time_taken = max(1, int(now_ts - started_at))
                    add_exercise(user_id, exercise, current_reps, 0, time_taken)

                if st.session_state.voice_pipeline:
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_completed",
                        exercise=exercise,
                        metrics={}
                    )
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result

                st.rerun()

        if workout_started:
            st.divider()

            exercise = st.session_state.get("exercise_type")
            total_reps = st.session_state.get("reps", 0)
            current_set_reps = st.session_state.get("current_set_reps", 0)
            reps_per_set = st.session_state.get("reps_per_set", 0)
            sets_completed = st.session_state.get("sets_completed", 0)
            target_sets = st.session_state.get("target_sets", 0)

            st.subheader("Progress")

            st.metric("Total Reps", f"{total_reps}")
            st.metric("Current Set Reps", f"{current_set_reps} / {reps_per_set}")
            st.metric("Sets Completed", f"{sets_completed} / {target_sets}")

            st.divider()

            if exercise == "Squats":
                st.subheader("Squat Metrics")
                st.metric("Knee Angle", f"{st.session_state.get('knee_angle', 0)}°")
                st.metric("Back Angle", f"{st.session_state.get('back_angle', 0)}°")
                st.metric("Depth Status", st.session_state.get('depth_status', 'N/A'))

            elif exercise == "Push-ups":
                st.subheader("Push-up Metrics")
                st.metric("Elbow Angle", f"{st.session_state.get('elbow_angle', 0)}°")
                st.metric("Body Alignment", st.session_state.get('body_alignment', 'N/A'))
                st.metric("Hip Position", st.session_state.get('hip_status', 'N/A'))

            elif exercise == "Biceps Curls (Dumbbell)":
                st.subheader("Curl Metrics")
                st.metric("Elbow Angle", f"{st.session_state.get('elbow_angle', 0)}°")
                st.metric("Shoulder Stability", st.session_state.get('shoulder_status', 'N/A'))
                st.metric("Swing Detection", st.session_state.get('swing_status', 'N/A'))

            elif exercise == "Shoulder Press":
                st.subheader("Shoulder Press Metrics")
                st.metric("Elbow Angle", f"{st.session_state.get('elbow_angle', 0)}°")
                st.metric("Arm Extension", st.session_state.get('extension_status', 'N/A'))
                st.metric("Back Arch", st.session_state.get('back_arch_status', 'N/A'))

            elif exercise == "Lunges":
                st.subheader("Lunge Metrics")
                st.metric("Front Knee Angle", f"{st.session_state.get('front_knee_angle', 0)}°")
                st.metric("Torso Angle", f"{st.session_state.get('torso_angle', 0)}°")
                st.metric("Balance Status", st.session_state.get('balance_status', 'N/A'))

    st.title("AI Real-time GYM Coach")
    st.markdown("#### Real-time pose detection with proactive AI voice coaching")
 
    # Keep a stable slot so queuing a coach line never shifts the WebRTC
    # component, and keep the clip mounted so the frequent automatic reruns
    # (every ~0.25s while streaming) do not tear the player down and cut the
    # speech off mid-sentence.
    audio_slot = st.empty()
    if st.session_state.get("audio_to_play"):
        autoplay_audio(st.session_state.audio_to_play, container=audio_slot)

    if st.session_state.get("coach_feedback"):
        st.markdown("")
        st.success(f"🤖 **Coach:** {st.session_state.coach_feedback}")

    if not workout_started:
        st.markdown(
            """
            <div style="
                border: 2px dashed rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 48px 32px;
                text-align: center;
                color: #888;
                margin-top: 32px;
                margin-bottom: 32px;
                background: rgba(255, 255, 255, 0.02);
            ">
                <h2 style="color:#eee; margin-bottom:8px;">👈 Set your workout plan</h2>
                <p style="font-size:1.05rem; color:#aaa;">
                    Choose your exercise, sets and reps in the sidebar,<br>
                    then click <strong>Start Workout</strong> to activate camera and AI coach.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        if not CAMERA_RUNTIME_SUPPORTED:
            st.warning(
                "Live camera analysis is disabled on macOS because the native "
                "OpenCV and WebRTC libraries can crash the Python process. "
                "The workout planner and coach remain available."
            )
            st.info(
                "Use the deployed Streamlit app or a Linux environment for "
                "real-time pose tracking."
            )
        elif webrtc_streamer is None or WebRtcMode is None:
            st.warning(
                "Live camera coaching is unavailable in this environment because the WebRTC dependency is missing or incompatible. "
                "The workout planner and coaching flow still work without the camera feed."
            )
            st.info("Install a compatible `streamlit-webrtc` stack to enable real-time pose tracking.")
        else:
            try:
                from services.vision.exercise_video_processor import VideoProcessorClass
            except Exception:
                VideoProcessorClass = None

            if VideoProcessorClass is None:
                st.warning("Camera analysis is unavailable because the video processor could not be initialized.")
            else:
                # More flexible WebRTC config for localhost and deployment
                rtc_config = {
                    "iceServers": [
                        {"urls": ["stun:stun.l.google.com:19302"]},
                        {"urls": ["stun:stun1.l.google.com:19302"]},
                        {"urls": ["stun:stun2.l.google.com:19302"]},
                        {"urls": ["stun:stun3.l.google.com:19302"]},
                    ]
                }
                # Try to use better config for deployment
                try:
                    from streamlit_webrtc import RTCConfiguration
                    rtc_config_obj = RTCConfiguration(iceServers=rtc_config["iceServers"])
                    rtc_config_arg = rtc_config_obj
                except Exception:
                    rtc_config_arg = rtc_config

                try:
                    context = webrtc_streamer(
                        key="exercise-analysis",
                        mode=WebRtcMode.SENDRECV,
                        video_processor_factory=VideoProcessorClass,
                        rtc_configuration=rtc_config_arg,
                        media_stream_constraints={
                            "video": {
                                "width": {"min": 640, "ideal": 1280, "max": 1920},
                                "height": {"min": 480, "ideal": 720, "max": 1080},
                                "facingMode": "user"
                            },
                            "audio": False
                        },
                        async_processing=True
                    )
                except Exception as webrtc_err:
                    try:
                        context = webrtc_streamer(
                            key="exercise-analysis",
                            mode=WebRtcMode.SENDRECV,
                            video_processor_factory=VideoProcessorClass,
                            rtc_configuration=rtc_config_arg,
                            media_stream_constraints={
                                "video": True,
                                "audio": False
                            },
                            async_processing=False
                        )
                    except Exception as webrtc_err2:
                        st.error(f"Camera initialization failed: {webrtc_err}")
                        st.info("Try refreshing the page or check your browser's camera permissions.")
                        raise

                sync_metrics_update(context)

                if st.session_state.get("workout_completed"):
                    # Workout finished: stop the camera and return to the planner.
                    st.session_state.workout_started = False
                    time.sleep(0.5)
                    st.rerun()

                if context.state.playing:
                    time.sleep(0.25)
                    st.rerun()

                inject_webrtc_styles()

    st.divider()

    st.markdown("#### Workout History")

    user_id = st.session_state.get("user_id", 0)

    if isinstance(user_id, int):
        history_rows = get_users_exercises(user_id)

        arr = [
            {
                "Exercise": row['exercise_name'],
                "Reps": row['reps'],
                "Sets": row['sets'],
                "Time (sec)": row['time'],
                "Date": row['created_at']
            }
            for row in history_rows
        ]

        df = pd.DataFrame(arr)

        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
            agg_df = df.groupby(["Exercise", "Date"]).agg({
                "Reps": 'sum',
                "Sets": "sum",
                "Time (sec)": "sum"
            }).reset_index()
            agg_df.index += 1
            st.table(agg_df, border="horizontal")
        else:
            st.info("No workout history found yet. Complete your first set to log stats!")


if __name__ == "__main__":
    main()