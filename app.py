import io, json, zipfile, os, tempfile
import streamlit as st
from pypdf import PdfReader

from pii import redact_text
from image_tools import blur_faces
from pdf_tools import extract_images, extract_text
from audio_utils import transcribe_with_words, spans_to_time_ranges, bleep_audio
from video_utils import blur_video_faces_opencv, extract_audio_ffmpeg, mux_audio_ffmpeg

st.set_page_config(page_title="Privasee Pro v2 — Multimodal PII Anonymizer", page_icon="🔒", layout="wide")

st.title("🔒 Privasee Pro v2 — Multimodal PII Anonymizer")
st.caption("Local-only • No PyAV/MoviePy • Text, Images, PDFs, Audio, and Video")

with st.sidebar:
    st.header("Redaction")
    mode = st.selectbox("Mode", ["mask", "pseudo", "hash"], index=0)
    level = st.selectbox("Privacy level", ["light", "standard", "strict"], index=1)
    kernel = st.slider("Face blur kernel", 15, 71, 31, 2)
    st.markdown("---")
    st.write("Video/Audio need **ffmpeg** on PATH (`brew install ffmpeg`).")

tab_t, tab_i, tab_p, tab_a, tab_v = st.tabs(["🔤 Text", "🖼 Images", "📄 PDF", "🎧 Audio", "🎬 Video"])

with tab_t:
    st.subheader("Redact Text")
    text = st.text_area("Input", placeholder="Paste text...", height=200)
    if st.button("Redact Text", type="primary"):
        res = redact_text(text or "", mode=mode, level=level)
        st.markdown("**Output**")
        st.code(res["text"], language="text")
        st.markdown("**Privacy Report**")
        st.json({"counts": res["counts"], "residual_risk": res["residual_risk"], "mode": mode, "level": level})
        st.download_button("⬇️ Download redacted.txt", data=res["text"].encode("utf-8"), file_name="redacted.txt")

with tab_i:
    st.subheader("Redact Image (Face Blur)")
    up_img = st.file_uploader("Choose an image", type=["png","jpg","jpeg","webp"])
    if up_img and st.button("Redact Image", type="primary"):
        b = up_img.read()
        res = blur_faces(b, kernel=kernel)
        st.markdown(f"**Faces blurred**: {res['faces']}")
        c1, c2 = st.columns(2)
        with c1: st.image(b, caption="Original", use_column_width=True)
        with c2: st.image(res["image"], caption="Redacted", use_column_width=True)
        st.download_button("⬇️ Download redacted.png", data=res["image"], file_name="redacted.png", mime="image/png")

with tab_p:
    st.subheader("Redact PDF (text + embedded images)")
    up_pdf = st.file_uploader("Choose a PDF", type=["pdf"])
    if up_pdf and st.button("Redact PDF", type="primary"):
        pdf_bytes = up_pdf.read()
        reader = PdfReader(io.BytesIO(pdf_bytes))

        text = extract_text(reader)
        t_res = redact_text(text, mode=mode, level=level)

        images = extract_images(reader)
        redacted_images = []
        for img in images:
            try:
                r = blur_faces(img["bytes"], kernel=kernel)
                redacted_images.append({"name": img["name"].rsplit(".",1)[0] + "_redacted.png", "bytes": r["image"], "faces": r["faces"], "page": img["page"]})
            except Exception:
                pass

        report = {
            "text_counts": t_res["counts"],
            "text_residual_risk": t_res["residual_risk"],
            "num_images": len(images),
            "num_images_redacted": len(redacted_images),
            "mode": mode, "level": level,
        }

        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("redacted_text.txt", t_res["text"])
            z.writestr("privacy_report.json", json.dumps(report, indent=2))
            for im in redacted_images:
                z.writestr(f"images/{im['name']}", im["bytes"])
        mem.seek(0)

        st.success("PDF processed. Download bundle below.")
        st.download_button("⬇️ Download redacted_bundle.zip", data=mem, file_name="redacted_bundle.zip", mime="application/zip")

with tab_a:
    st.subheader("Redact Audio (bleep/mute PII spans)")
    up_aud = st.file_uploader("Choose audio", type=["wav","mp3","m4a","aac","flac","ogg"])
    bleep = st.checkbox("Bleep (on) / Mute (off)", value=True)
    if up_aud and st.button("Redact Audio", type="primary"):
        with tempfile.TemporaryDirectory() as td:
            src_path = os.path.join(td, up_aud.name)
            with open(src_path, "wb") as f: f.write(up_aud.read())

            transcript, words = transcribe_with_words(src_path)
            res = redact_text(transcript, mode=mode, level=level)

            # naive char-span diff for masked output
            spans = []
            i = 0; j = 0; red = res["text"]
            while i < len(transcript) and j < len(red):
                if red[j] == transcript[i]:
                    i += 1; j += 1; continue
                if red[j] == "*":
                    s = i
                    while j < len(red) and red[j] == "*": j += 1
                    while i < len(transcript) and (j >= len(red) or (transcript[i] != red[j])): i += 1
                    spans.append((s, i))
                else:
                    i += 1; j += 1

            times = spans_to_time_ranges(spans, words)
            out_audio = bleep_audio(src_path, times)
            out_path = os.path.join(td, "redacted_audio.wav")
            out_audio.export(out_path, format="wav")

            st.audio(out_path)
            st.markdown("**Transcript (redacted)**")
            st.code(res["text"])
            with open(out_path, "rb") as f:
                st.download_button("⬇️ Download redacted_audio.wav", data=f.read(), file_name="redacted_audio.wav", mime="audio/wav")

with tab_v:
    st.subheader("Redact Video (face blur; optional audio bleep)")
    up_vid = st.file_uploader("Choose video", type=["mp4","mov","mkv","webm"])
    do_bleep = st.checkbox("Also bleep audio using ASR", value=False)
    if up_vid and st.button("Redact Video", type="primary"):
        with tempfile.TemporaryDirectory() as td:
            src_path = os.path.join(td, up_vid.name)
            with open(src_path, "wb") as f: f.write(up_vid.read())

            # blur faces in video frames
            video_noaudio = os.path.join(td, "video_blurred.mp4")
            blur_video_faces_opencv(src_path, video_noaudio, kernel=kernel)

            if do_bleep:
                aud_path = os.path.join(td, "orig.wav")
                extract_audio_ffmpeg(src_path, aud_path)
                transcript, words = transcribe_with_words(aud_path)
                res = redact_text(transcript, mode=mode, level=level)

                spans = []
                i = 0; j = 0; red = res["text"]
                while i < len(transcript) and j < len(red):
                    if red[j] == transcript[i]:
                        i += 1; j += 1; continue
                    if red[j] == "*":
                        s = i
                        while j < len(red) and red[j] == "*": j += 1
                        while i < len(transcript) and (j >= len(red) or (transcript[i] != red[j])): i += 1
                        spans.append((s, i))
                    else:
                        i += 1; j += 1

                times = spans_to_time_ranges(spans, words)
                from pydub import AudioSegment
                out_aud_seg = bleep_audio(aud_path, times)
                bleeped_aud = os.path.join(td, "bleeped.wav")
                out_aud_seg.export(bleeped_aud, format="wav")
                final_video = os.path.join(td, "video_redacted.mp4")
                mux_audio_ffmpeg(video_noaudio, bleeped_aud, final_video)
                st.video(final_video)
                with open(final_video, "rb") as f:
                    st.download_button("⬇️ Download redacted_video.mp4", data=f.read(), file_name="redacted_video.mp4", mime="video/mp4")
            else:
                st.video(video_noaudio)
                with open(video_noaudio, "rb") as f:
                    st.download_button("⬇️ Download redacted_video.mp4", data=f.read(), file_name="redacted_video.mp4", mime="video/mp4")
