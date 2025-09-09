import threading, time, sys, os, re, subprocess
import pyperclip
import pystray
from collections import deque
from PIL import Image, ImageDraw, ImageFont
from winotify import Notification, audio
from yt_dlp import YoutubeDL

# ---------------- RESOURCE PATH ----------------
def resource_path(relative_path):
    """
    Get absolute path to resource.
    Works in dev and with PyInstaller.
    """
    if hasattr(sys, "_MEIPASS"):  # PyInstaller sets this
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
# ---------------- ICON PATH ----------------
ICON_PATH = resource_path("icons/icon.png")

# ---------------- QUEUE & DOWNLOAD FLAG ----------------
download_queue = deque()  # URLs waiting to download
queue_titles = []         # Store tuples of (title, url)
dlInProgress = False      # Flag to prevent multiple concurrent downloads
queue_lock = threading.Lock()  # Lock to safely access the queue

# ---------------- PATH FOR FFMPEG ----------------
def ffmpegPath():
    """Return path to bundled ffmpeg binary."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(base_dir, "bin")
    return os.path.join(bin_dir, "ffmpeg.exe")

# ---------------- YOUTUBE URL REGEX ----------------
YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+)"

# ---------------- CREATE PROGRESS ICON ----------------
def create_icon(progress=0, size=64):
    """
    Create a circular progress icon with percentage text.
    - Green arc shows download progress.
    - black text with white outline shows percentage.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw background circle
    draw.ellipse((0, 0, size, size), fill=(50, 50, 50, 255))

    # Draw progress arc
    start_angle = -90
    end_angle = start_angle + (progress / 100) * 360
    draw.pieslice((0, 0, size, size), start_angle, end_angle, fill=(0, 200, 0, 255))

    # Draw percentage text
    try:
        font = ImageFont.truetype("arial.ttf", int(size * 0.5))
    except:
        font = ImageFont.load_default()

    text = f"{int(progress)}%"
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (size - (bbox[2] - bbox[0])) / 2
    y = (size - (bbox[3] - bbox[1])) / 2

    # Draw black outline
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill="white")
    # Draw white text
    draw.text((x, y), text, font=font, fill="black")

    return img

# ---------------- WINDOWS NOTIFICATION ----------------
def toaster(title, message, icon_path=ICON_PATH, button=None):
    """
    Show a Windows toast notification.
    - Optional 'button' can be a tuple: (label, launch_url)
    """
    toast = Notification(
        app_id="vacuum",
        title=title,
        msg=message,
        duration="short",
        icon=icon_path
    )
    toast.set_audio(audio.Default, loop=False)
    if button:
        toast.add_actions(label=button[0], launch=button[1])
    toast.show()

# ---------------- YTDLP PROGRESS HOOK ----------------
def progress_hook(d, icon):
    """
    Update tray icon and tooltip based on yt-dlp download progress.
    - Removes finished downloads from the queue_titles list.
    """
    status = d.get("status")
    filename = d.get("filename", "Unknown")
    percent = 0
    try:
        if d.get("total_bytes") and d.get("downloaded_bytes") is not None:
            percent = int(d["downloaded_bytes"] / d["total_bytes"] * 100)
        else:
            percent_str = d.get("_percent_str", "0.0")
            percent = int(float(percent_str.strip("%")))
    except:
        percent = 0
    percent = max(0, min(percent, 100))

    if status == "downloading":
        icon.title = f"{filename} - {percent}%"
        icon.icon = create_icon(progress=percent)
    elif status == "finished":
        icon.title = f"Downloaded: {filename}"
        icon.icon = create_icon(progress=100)
        with queue_lock:
            queue_titles[:] = [(t, u) for t, u in queue_titles if t != filename]

# ---------------- DOWNLOAD VIDEO ----------------
def download_video(url: str, icon):
    """
    Download YouTube video in Premiere-friendly format:
    H.264 video + AAC audio in MP4 container.
    Only re-encode if needed.
    """
    global dlInProgress
    ffmpeg = ffmpegPath()
    downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")

    ydlConfig = {
        "ffmpeg_location": ffmpeg,
        "outtmpl": os.path.join(os.path.expanduser("~"), "Downloads", "%(title)s.%(ext)s"),
        "format": "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]",
        "merge_output_format": "mp4",
        "progress_hooks": [lambda d: progress_hook(d, icon)],
    }

    try:
        with YoutubeDL(ydlConfig) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "Unknown")
            downloaded_file = ydl.prepare_filename(info)

        # Check codec to decide if re-encoding is necessary
        probe = subprocess.run(
            [ffmpeg, "-i", downloaded_file],
            capture_output=True, text=True
        ).stderr

        # Re-encode if video is not H.264 or audio not AAC
        if "Video: av1" in probe or "Video: vp9" in probe or "Audio: aac" not in probe:
            final_file = os.path.join(DOWNLOADS_DIR, f"{title}_reencoded.mp4")
            subprocess.run([
                ffmpeg,
                "-i", downloaded_file,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-strict", "experimental",
                final_file
            ])
            toaster("✅ Downloaded & Re-encoded", f"{title}")
        else:
            toaster("✅ Downloaded", f"{title}")

    except Exception as e:
        toaster("❌ Failure", str(e))
    finally:
        dlInProgress = False


# ---------------- QUEUE WORKER ----------------
def queue_worker(icon):
    """
    Continuously checks the queue and downloads the next video if not already downloading.
    """
    global dlInProgress
    while True:
        url = None
        with queue_lock:
            if download_queue and not dlInProgress:
                url = download_queue.popleft()
                dlInProgress = True

        if url:
            icon.icon = create_icon(progress=0)
            icon.title = "Starting download..."
            download_video(url, icon)
        else:
            time.sleep(0.5)

# ---------------- CLIPBOARD MONITOR ----------------
def clipboard_monitor(icon):
    """
    Continuously monitors clipboard for YouTube URLs and adds them to the queue.
    - Shows position in queue in notifications.
    """
    last_clipboard = None
    while True:
        try:
            text = pyperclip.paste()
            if text != last_clipboard:
                last_clipboard = text
                match = re.search(YOUTUBE_REGEX, text)
                if match:
                    url = match.group(0)
                    ffmpeg = ffmpegPath()
                    ydlConfig = {"ffmpeg_location": ffmpeg}
                    try:
                        with YoutubeDL(ydlConfig) as ydl:
                            info = ydl.extract_info(url, download=False)
                            title = info.get("title", "Unknown")
                    except:
                        title = "Unknown"

                    with queue_lock:
                        if url not in [u for t, u in queue_titles]:
                            download_queue.append(url)
                            queue_titles.append((title, url))
                            pos = len(download_queue)
                            toaster("📋 Queued", f"{title} - {pos}{ordinal(pos)} in queue")
            time.sleep(1)
        except Exception as e:
            toaster("❌ Error", str(e))
            time.sleep(1)

# ---------------- HELPER FUNCTIONS ----------------
def ordinal(n):
    """Return ordinal string for a number (1 -> 'st', 2 -> 'nd', etc.)."""
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

def infoNotif(icon_, item):
    """Send a sample interactive notification with a button and icon."""
    toaster(
        "vacuum. it sucks.",
        "when a vibecoded downloader solos every other one -same 2025",
        icon_path=ICON_PATH,
        button=("Go to YouTube", "https://www.youtube.com/@2same2furious")
    )

def on_quit(icon_, item):
    """Quit the tray app."""
    icon_.stop()

# ---------------- MAIN APP ----------------
def main():
    menu = pystray.Menu(
        pystray.MenuItem("What is this?", infoNotif),
        pystray.MenuItem("Kill", on_quit)
    )

    icon = pystray.Icon("vacuum")
    icon.icon = create_icon(0)
    icon.title = "vacuum"
    icon.menu = menu

    # Start clipboard monitoring and queue worker in background threads
    threading.Thread(target=clipboard_monitor, args=(icon,), daemon=True).start()
    threading.Thread(target=queue_worker, args=(icon,), daemon=True).start()
    icon.run()

# ---------------- ENTRY POINT ----------------
if __name__ == "__main__":
    main()
