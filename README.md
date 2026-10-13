# AI Real-time GYM Coach 🏋️‍♂️

A real-time computer vision workout coach and posture analyzer that tracks exercise repetitions, evaluates biomechanical form, and delivers proactive voice coaching cues using **MediaPipe**, **Streamlit-WebRTC**, **Groq LLM**, and **gTTS**.

Includes a modern dark-themed **Landing Page** with an interactive pose telemetry simulator, pre-configured for Netlify deployment.

---

## 🌐 Live Demo

- **Landing Page / Project Site:** [ai-gym-trainer-avartan.netlify.app](https://ai-gym-trainer-avartan.netlify.app)
- **Web App (Streamlit):** [ai-gym-trainer-avartan.streamlit.app](https://ai-gym-trainer-avartan.streamlit.app)

---

## 🚀 Key Features

- **Real-Time Pose Landmark Tracking**: Leverages Google MediaPipe's 33-keypoint pose landmark task for sub-35ms joint angle detection.
- **5 Supported Exercises**:
  - **Squats**: Evaluates knee flexion angle and 100° depth threshold, preventing partial reps.
  - **Push-ups**: Monitors elbow angle alongside spinal alignment and hip sag / piked posture.
  - **Biceps Curls**: Isolates peak flexion, detecting elbow drift and torso swing momentum.
  - **Shoulder Press**: Tracks full overhead lockout and monitors lumbar spine hyperextension.
  - **Lunges**: Measures front knee flexion angle and lateral hip-to-shoulder balance symmetry.
- **Proactive AI Voice Coach**:
  - Powered by high-speed Groq LLMs (Qwen / LLaMA) with streaming responses converted to speech via Google TTS (`gTTS`).
  - Seamless fallback to smart built-in athletic cues if offline or without an API key.
- **Workout Logging & Analytics**: Automatically persists sets, reps, duration, and exercise timestamps into an SQLite database with aggregated historical summaries.
- **Modern Landing Page**:
  - Built with responsive HTML5, CSS3, and Vanilla JavaScript.
  - Features real athletic movement telemetry visuals and an interactive in-browser 60 FPS skeleton simulator.
  - Configured for 1-click Netlify deployment (`netlify.toml`).

---

## 📂 Project Structure

```text
AI-Gym/
├── MainApp/                         # Primary Streamlit WebRTC application
│   ├── core/                        # Abstract exercise base classes
│   │   └── base_exercise.py
│   ├── detectors/                   # Biomechanical rule detectors
│   │   ├── biceps_curl.py
│   │   ├── lunges.py
│   │   ├── pushup.py
│   │   ├── shoulder_press.py
│   │   └── squat.py
│   ├── ml_models/                   # MediaPipe pose model assets
│   │   └── pose_landmarker_full.task
│   ├── services/
│   │   ├── auth/                    # Session login wall
│   │   ├── coaching/                # Groq LLM & TTS voice pipeline
│   │   ├── config/                  # Exercise constants & prompt engineering
│   │   ├── persistence/             # SQLite repository & schema
│   │   ├── state/                   # Streamlit session state defaults
│   │   ├── tracking/                # Live rep counter & metric synchronization
│   │   ├── ui/                      # Styles and font injectors
│   │   └── vision/                  # WebRTC VideoProcessorClass
│   ├── static/                      # Custom fonts & CSS theme
│   ├── .env.example                 # Environment variables template
│   ├── main.py                      # Streamlit application entry point
│   ├── packages.txt                 # Linux system dependencies for Streamlit Cloud
│   └── requirements.txt             # Python package dependencies
│
├── LandingPage/                     # Modern showcase landing page
│   ├── fonts/                       # Brand webfonts
│   ├── images/                      # Curated athletic movement photography
│   ├── index.html                   # Landing page markup & interactive canvas simulator
│   ├── style.css                    # Dark-mode athletic design system
│   └── netlify.toml                 # Netlify deployment configuration
│
├── .gitignore                       # Production-grade git hygiene
└── README.md                        # Documentation
```

---

## 🛠️ Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/avartan007/AI-GYM-Trainer.git
cd AI-GYM-Trainer
```

### 2. Run the Main App (Streamlit)

```bash
cd MainApp

# Create and activate virtual environment (Python 3.12 is recommended)
python3.12 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure your Groq API Key for AI voice coaching
cp .env.example .env
# Edit .env and paste your key: GROQ_API_KEY=gsk_...

# Start the Streamlit server
streamlit run main.py
```

The application will start at `http://localhost:8501`. Allow camera access when prompted by the browser.

If your machine only has Python 3.13, install Python 3.12 for this project first.
MediaPipe's stable 0.10.x wheel is the supported computer-vision dependency used by
the app; the previous 0.10.14 pin was not available for newer Python versions.

On macOS, the local app intentionally keeps live camera processing disabled when
the native OpenCV and WebRTC libraries would conflict and crash Python. The
deployed Streamlit Community Cloud app runs on Linux and keeps the real-time
camera path enabled.

### 3. Run the Landing Page

Simply open `LandingPage/index.html` in any web browser, or serve it using Python:

```bash
cd LandingPage
python3 -m http.server 3000
```

Open `http://localhost:3000` to interact with the landing page and the live vector skeleton simulator.

---

## 🌐 Deployment Guide

### Deploying the Main App on Streamlit Community Cloud

1. Push your repository to GitHub.
2. Sign in to [share.streamlit.io](https://share.streamlit.io/).
3. Select your repository: `avartan007/AI-GYM-Trainer`.
4. Set the **Main file path** to: `MainApp/main.py`.
5. Under **Advanced Settings** -> **Secrets**, add your Groq API key:
   ```toml
   GROQ_API_KEY = "gsk_your_groq_api_key_here"
   ```
6. Click **Deploy**. `packages.txt` will automatically install the necessary OpenCV and OpenGL system libraries.

### Deploying the Landing Page on Netlify

1. Sign in to [Netlify](https://app.netlify.com/).
2. Click **Add new site** -> **Import an existing project** from GitHub.
3. Select `avartan007/AI-GYM-Trainer`.
4. Configure the build settings:
   - **Base directory**: `LandingPage`
   - **Publish directory**: `LandingPage` (or `.`)
5. Click **Deploy site**.
6. Update `MAIN_APP_URL` in `LandingPage/index.html` and the `/app` redirect in
   `netlify.toml` with your live Streamlit URL.

Netlify hosts the static landing page only; it does not run the Python/Streamlit
server. The landing page connects to the main app through the two `Launch App`
links and the `/app` redirect. Deploy `MainApp/main.py` separately on Streamlit
Community Cloud, then copy that public URL into those two locations.

The landing-page simulator is shipped as a minified JavaScript asset to reduce
casual copying and keep the HTML readable. Because the browser must receive and
execute this code, no public static site can make client-side animation source
truly secret. The simulator's coach voice is browser speech synthesis: visitors
must click **Enable coach voice** once because browsers block unexpected autoplay.

---

## 🔑 Environment Variables

| Variable | Description | Required |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | Groq API Key for dynamic LLaMA / Qwen AI coaching cues | Optional (Falls back to built-in athletic cues if omitted) |

---

## 👤 Author

**Avartan Athlay**
- GitHub: [@avartan007](https://github.com/avartan007)
- Repository: [AI-GYM-Trainer](https://github.com/avartan007/AI-GYM-Trainer)
- LinkedIn: [Avartan Athlay](https://www.linkedin.com/in/avartanathlay)
- Email: [avartanathlay@gmail.com](mailto:avartanathlay@gmail.com)

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
