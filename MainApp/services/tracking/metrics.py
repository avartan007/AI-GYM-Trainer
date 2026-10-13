import streamlit as st
import time
from services.config.workout_config import METRICS_FIELDS
from services.persistence.exercise_repository import add_exercise


# How long the coach stays quiet after a set before nudging the user to start
# the next set. Kept short so the user is not left guessing.
REST_SECONDS = 20


def _speak(event, exercise, metrics):
    """Ask the voice pipeline for one line and queue it for playback."""
    pipeline = st.session_state.get("voice_pipeline")

    if not pipeline:
        return

    result = pipeline.process_event(event=event, exercise=exercise, metrics=metrics)

    if result:
        st.session_state.audio_to_play, st.session_state.coach_feedback = result


def _announce_workout_completed(exercise, metrics):
    if st.session_state.get("last_notified_workout_complete", False):
        return

    st.session_state.last_notified_workout_complete = True
    _speak("workout_completed", exercise, metrics)


def sync_metrics_update(context):
    if not context or not hasattr(context, "state") or not context.state.playing:
        return

    processor = getattr(context, "video_processor", None)

    if not processor:
        return

    exercise = st.session_state.get("exercise_type")

    if not exercise:
        return

    # Once the workout is finished we stop tracking and stay quiet.
    if st.session_state.get("workout_completed"):
        return

    processor.set_exercise(exercise)
    latest_metrics = processor.get_latest_metrics()

    if not latest_metrics:
        return

    reps = latest_metrics.get("reps", 0) or 0
    st.session_state.reps = reps

    fields = METRICS_FIELDS.get(exercise)

    if not fields:
        return

    for key, default in fields.items():
        st.session_state[key] = latest_metrics.get(key, default)

    reps_per_set = st.session_state.get("reps_per_set", 0)
    target_sets = st.session_state.get("target_sets", 0)
    now_ts = time.time()

    if reps_per_set > 0 and target_sets > 0:
        sets_completed = reps // reps_per_set
        current_set_reps = reps % reps_per_set
        workout_completed = sets_completed >= target_sets
    else:
        sets_completed = 0
        current_set_reps = 0
        workout_completed = False

    st.session_state.sets_completed = sets_completed
    st.session_state.current_set_reps = current_set_reps
    st.session_state.workout_completed = workout_completed

    last_saved_sets = st.session_state.get("last_saved_sets_completed", 0)

    if sets_completed > last_saved_sets:
        newly_completed = sets_completed - last_saved_sets
        started_at = st.session_state.get("set_cycle_started_at", now_ts)
        time_taken = max(1, int(now_ts - started_at))
        user_id = st.session_state.get("user_id", 0)

        add_exercise(user_id, exercise, newly_completed * reps_per_set, newly_completed, time_taken)

        st.session_state.set_cycle_started_at = now_ts
        st.session_state.last_saved_sets_completed = sets_completed

        if workout_completed:
            _announce_workout_completed(exercise, latest_metrics)
        else:
            # Exactly one cue per finished set, then start a rest window.
            _speak("set_completed", exercise, latest_metrics)
            st.session_state.rest_started_at = now_ts
            st.session_state.next_set_announced = False

        return

    if workout_completed:
        _announce_workout_completed(exercise, latest_metrics)
        return

    # Nudge the user to start the next set once the rest window has elapsed.
    rest_started_at = st.session_state.get("rest_started_at", 0.0)

    if rest_started_at and not st.session_state.get("next_set_announced", False):
        if now_ts - rest_started_at >= REST_SECONDS:
            st.session_state.next_set_announced = True
            _speak("start_next_set", exercise, latest_metrics)
            return

    # As soon as the user resumes, clear the rest state so the next set's
    # tracking starts clean.
    if current_set_reps > 0:
        st.session_state.rest_started_at = 0.0
        st.session_state.next_set_announced = False

    pose_detected = latest_metrics.get("pose_detected", True)

    if not pose_detected:
        _speak(
            "no_pose_detected",
            exercise,
            {"issue": "No pose detected! Please step into the camera frame."},
        )
        return

    _speak("ongoing_form_check", exercise, latest_metrics)
