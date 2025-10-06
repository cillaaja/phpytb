import sys
import subprocess
import threading
import os
import time
import requests
import streamlit.components.v1 as components

# Pastikan Streamlit terpasang
try:
    import streamlit as st
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit"])
    import streamlit as st


# ======================== #
#  🔹 Cek ketersediaan FFmpeg #
# ======================== #
def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


# ======================== #
#  🔹 Fungsi FFmpeg Stream #
# ======================== #
def run_ffmpeg(video_path, stream_key, is_shorts, log_callback):
    output_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
    scale = "-vf scale=720:1280" if is_shorts else ""

    cmd = [
        "ffmpeg", "-re", "-stream_loop", "-1", "-i", video_path,
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k",
        "-maxrate", "2500k", "-bufsize", "5000k",
        "-g", "60", "-keyint_min", "60",
        "-c:a", "aac", "-b:a", "128k",
        "-f", "flv"
    ]
    if scale:
        cmd += scale.split()
    cmd.append(output_url)

    log_callback(f"Menjalankan FFmpeg: {' '.join(cmd)}")

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        st.session_state['ffmpeg_process'] = process
        for line in process.stdout:
            log_callback(line.strip())
        process.wait()
    except Exception as e:
        log_callback(f"Error: {e}")
    finally:
        log_callback("⚠️ Streaming selesai atau dihentikan.")


# ============================ #
#  🔹 Simpan File Upload Cepat #
# ============================ #
def save_large_file(uploaded_file, save_path):
    CHUNK_SIZE = 4 * 1024 * 1024  # 4MB per tulis
    total = 0
    progress_bar = st.progress(0, text="📀 Menyimpan video ke disk...")

    with open(save_path, "wb") as f:
        while True:
            chunk = uploaded_file.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            progress_bar.progress(min(1.0, total / (512 * 1024 * 1024)),
                                  text=f"Menulis data... {total / (1024*1024):.1f} MB tersimpan")
    progress_bar.empty()
    return save_path


# =============================== #
#  🔹 Unduh Video dari URL besar  #
# =============================== #
def download_video_from_url(url, save_path, log_callback):
    log_callback(f"📥 Mengunduh video dari: {url}")
    try:
        if "drive.google.com" in url:
            if "id=" in url:
                file_id = url.split("id=")[-1]
            else:
                file_id = url.split("/d/")[1].split("/")[0]
            url = f"https://drive.google.com/uc?export=download&id={file_id}"

        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total_length = r.headers.get("content-length")
            total_length = int(total_length) if total_length else None
            downloaded = 0
            progress = st.progress(0, text="📡 Mengunduh video...")

            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=4 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_length:
                            progress.progress(min(1.0, downloaded / total_length),
                                              text=f"Mengunduh... {downloaded / (1024*1024):.1f} MB / {total_length / (1024*1024):.1f} MB")
            progress.empty()
        log_callback("✅ Unduhan selesai!")
        return True
    except Exception as e:
        log_callback(f"❌ Gagal mengunduh video: {e}")
        return False


# ====================== #
#  🔹 Fungsi Utama App  #
# ====================== #
def main():
    st.set_page_config(page_title="Streaming YouTube Live", page_icon="🎥", layout="wide")
    st.title("🎥 Streaming YouTube Live")

    if not check_ffmpeg():
        st.error("❌ FFmpeg belum terinstal. Silakan instal terlebih dahulu (contoh: `sudo apt install ffmpeg` atau `choco install ffmpeg` di Windows).")
        return

    upload_dir = "uploaded_videos"
    os.makedirs(upload_dir, exist_ok=True)

    # Bersihkan file lama (>1 hari)
    now = time.time()
    for f in os.listdir(upload_dir):
        fp = os.path.join(upload_dir, f)
        if os.path.isfile(fp) and now - os.path.getmtime(fp) > 86400:
            os.remove(fp)

    # Iklan opsional
    if st.checkbox("Tampilkan Iklan", value=False):
        components.html("""
            <div style="background:#f0f2f6;padding:20px;border-radius:10px;text-align:center">
                <p style="color:#888">Iklan akan muncul di sini</p>
            </div>
        """, height=200)

    local_videos = [f for f in os.listdir(upload_dir) if f.endswith(('.mp4', '.flv'))]
    selected_video = st.selectbox("🎬 Pilih video yang tersedia:", ["(Pilih)"] + local_videos)

    uploaded_file = st.file_uploader("📤 Upload video baru (mp4/flv - codec H264/AAC)", type=['mp4', 'flv'])
    video_url = st.text_input("🌐 Atau masukkan URL video langsung (termasuk Google Drive)")

    log_placeholder = st.empty()
    logs = []

    def log_callback(msg):
        logs.append(msg)
        log_placeholder.text("\n".join(logs[-25:]))

    video_path = None

    if uploaded_file:
        file_path = os.path.join(upload_dir, uploaded_file.name)
        st.info("⏳ Menyimpan file video besar ke disk...")
        save_large_file(uploaded_file, file_path)
        st.success(f"✅ Video '{uploaded_file.name}' berhasil disimpan!")
        video_path = file_path

    elif video_url:
        file_name = os.path.basename(video_url.split("?")[0])
        if not file_name.endswith(('.mp4', '.flv')):
            file_name += ".mp4"
        file_path = os.path.join(upload_dir, file_name)
        if download_video_from_url(video_url, file_path, log_callback):
            video_path = file_path
            st.success(f"✅ Video dari URL berhasil diunduh: {file_name}")
        else:
            st.error("❌ Gagal mengunduh video dari URL.")

    elif selected_video and selected_video != "(Pilih)":
        video_path = os.path.join(upload_dir, selected_video)

    stream_key = st.text_input("🔑 Masukkan YouTube Stream Key", type="password")
    is_shorts = st.checkbox("📱 Mode Shorts (720x1280)")

    if 'ffmpeg_thread' not in st.session_state:
        st.session_state['ffmpeg_thread'] = None
    if 'ffmpeg_process' not in st.session_state:
        st.session_state['ffmpeg_process'] = None

    # Jalankan streaming
    if st.button("▶️ Jalankan Streaming"):
        if not video_path or not stream_key:
            st.error("❌ Harap pilih video atau isi Stream Key!")
        else:
            st.session_state['ffmpeg_thread'] = threading.Thread(
                target=run_ffmpeg, args=(video_path, stream_key, is_shorts, log_callback), daemon=True
            )
            st.session_state['ffmpeg_thread'].start()
            st.success("✅ Streaming dimulai ke YouTube!")

    # Stop streaming
    if st.button("⏹️ Stop Streaming"):
        proc = st.session_state.get('ffmpeg_process')
        if proc and proc.poll() is None:
            proc.terminate()
            log_callback("⚠️ Streaming dihentikan oleh pengguna.")
            st.warning("Streaming dihentikan.")
        else:
            os.system("pkill ffmpeg")
            st.warning("⚠️ Tidak ada proses FFmpeg aktif.")

    log_placeholder.text("\n".join(logs[-25:]))


if __name__ == "__main__":
    main()
