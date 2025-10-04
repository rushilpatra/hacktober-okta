# 🔒 Privasee Pro v2 — No PyAV/MoviePy

Processes **Text, Images, PDFs, Audio, Video** with Streamlit UI.
Avoids PyAV by using OpenCV for frames and ffmpeg executable for audio mux.

## Install
```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -U pip setuptools wheel
brew install ffmpeg
pip install -r requirements.txt
streamlit run app.py
```
