import streamlit as st
import yt_dlp
import os
import tempfile
from pathlib import Path
import threading
import time

# Initialize session state FIRST
if 'download_progress' not in st.session_state:
    st.session_state.download_progress = {}
if 'download_status' not in st.session_state:
    st.session_state.download_status = {}

# Page configuration
st.set_page_config(
    page_title="YouTube Batch Downloader",
    page_icon="📺",
    layout="wide"
)

st.title("📺 YouTube Batch Downloader")
st.markdown("Download multiple YouTube videos or extract audio with ease!")

# Create download directory
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

def progress_hook(d):
    """Progress hook for yt-dlp"""
    if d['status'] == 'downloading':
        filename = d.get('filename', 'Unknown')
        if '_percent_str' in d:
            percent = d['_percent_str'].strip()
            st.session_state.download_progress[filename] = percent
        elif 'downloaded_bytes' in d and 'total_bytes' in d:
            percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
            st.session_state.download_progress[filename] = f"{percent:.1f}%"
    elif d['status'] == 'finished':
        filename = d.get('filename', 'Unknown')
        st.session_state.download_progress[filename] = "100%"
        st.session_state.download_status[filename] = "✅ Complete"

def download_single_video(url, options, index):
    """Download a single video"""
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            # Get video info first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', f'Video_{index}')
            st.session_state.download_status[title] = "⏳ Starting..."
            
            # Download the video
            ydl.download([url])
            st.session_state.download_status[title] = "✅ Complete"
            
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        st.session_state.download_status[f"Video_{index}"] = error_msg

def validate_youtube_url(url):
    """Validate if URL is a valid YouTube URL"""
    youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com']
    return any(domain in url.lower() for domain in youtube_domains)

# Sidebar for options
st.sidebar.header("⚙️ Download Options")

# Download type selection
download_type = st.sidebar.radio(
    "Download Type:",
    ["Video", "Audio Only"],
    help="Choose whether to download video or extract audio only"
)

# Quality selection for video
if download_type == "Video":
    quality = st.sidebar.selectbox(
        "Video Quality:",
        ["best", "worst", "720p", "480p", "360p", "240p"],
        help="Select video quality preference"
    )
    
    format_selection = st.sidebar.selectbox(
        "Video Format:",
        ["mp4", "webm", "mkv", "any"],
        help="Preferred video format"
    )
else:
    audio_quality = st.sidebar.selectbox(
        "Audio Quality:",
        ["best", "320", "256", "192", "128"],
        help="Audio quality in kbps (best = highest available)"
    )
    
    audio_format = st.sidebar.selectbox(
        "Audio Format:",
        ["mp3", "m4a", "wav", "flac"],
        help="Audio format for extraction"
    )

# Main interface
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📝 YouTube URLs")
    urls_input = st.text_area(
        "Enter YouTube URLs (one per line):",
        height=200,
        placeholder="https://www.youtube.com/watch?v=example1\nhttps://www.youtube.com/watch?v=example2\nhttps://youtu.be/example3",
        help="Paste YouTube URLs here, each on a new line"
    )
    
    # Process URLs
    urls = []
    if urls_input:
        raw_urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
        valid_urls = []
        invalid_urls = []
        
        for url in raw_urls:
            if validate_youtube_url(url):
                valid_urls.append(url)
            else:
                invalid_urls.append(url)
        
        urls = valid_urls
        
        if invalid_urls:
            st.warning(f"⚠️ Invalid URLs detected: {len(invalid_urls)}")
            with st.expander("Show invalid URLs"):
                for invalid_url in invalid_urls:
                    st.text(f"❌ {invalid_url}")
        
        if valid_urls:
            st.success(f"✅ Valid URLs found: {len(valid_urls)}")

with col2:
    st.subheader("📊 Download Status")
    
    if st.session_state.download_status:
        for filename, status in st.session_state.download_status.items():
            st.text(f"{filename[:30]}...")
            st.text(status)
            if filename in st.session_state.download_progress:
                st.text(f"Progress: {st.session_state.download_progress[filename]}")
            st.divider()
    else:
        st.info("No downloads in progress")

# Download button and logic
st.subheader("🚀 Start Download")

if st.button("Start Batch Download", type="primary", disabled=not urls):
    if not urls:
        st.error("Please enter at least one valid YouTube URL")
    else:
        # Clear previous status
        st.session_state.download_progress = {}
        st.session_state.download_status = {}
        
        # Configure yt-dlp options
        base_options = {
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'no_warnings': False,
        }
        
        if download_type == "Audio Only":
            base_options.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': audio_format,
                    'preferredquality': audio_quality if audio_quality != 'best' else '0',
                }],
            })
        else:
            if quality == "best":
                format_string = 'best'
            elif quality == "worst":
                format_string = 'worst'
            else:
                format_string = f'best[height<={quality[:-1]}]'
            
            if format_selection != "any":
                format_string += f'[ext={format_selection}]'
            
            base_options['format'] = format_string
        
        # Start downloads
        progress_placeholder = st.empty()
        
        with st.spinner("Downloading videos..."):
            threads = []
            for i, url in enumerate(urls):
                thread = threading.Thread(
                    target=download_single_video,
                    args=(url, base_options.copy(), i+1)
                )
                threads.append(thread)
                thread.start()
            
            # Monitor progress
            while any(thread.is_alive() for thread in threads):
                time.sleep(1)
                # Force refresh of the status display
                st.rerun()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
        
        st.success("🎉 Batch download completed!")
        
        # Show download summary
        completed = sum(1 for status in st.session_state.download_status.values() if "✅" in status)
        failed = sum(1 for status in st.session_state.download_status.values() if "❌" in status)
        
        st.info(f"Summary: {completed} successful, {failed} failed out of {len(urls)} total")

# Instructions
st.subheader("📋 Instructions")
st.markdown("""
1. **Add URLs**: Paste YouTube URLs in the text area (one per line)
2. **Configure Options**: Choose download type, quality, and format in the sidebar
3. **Start Download**: Click the download button to begin batch processing
4. **Monitor Progress**: Watch the download status in real-time
5. **Find Files**: Downloaded files will be saved in the `downloads` folder

**Supported URL formats:**
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://m.youtube.com/watch?v=VIDEO_ID`
""")

# Requirements info


# Footer
st.markdown("---")
st.markdown("Made with ❤️ using Streamlit and yt-dlp")
