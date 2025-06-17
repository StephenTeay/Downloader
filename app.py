import streamlit as st
import yt_dlp
import os
from pathlib import Path
import concurrent.futures
import time
import queue
import threading

# Initialize session state FIRST
if 'download_results' not in st.session_state:
    st.session_state.download_results = []
if 'is_downloading' not in st.session_state:
    st.session_state.is_downloading = False

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

class DownloadProgress:
    def __init__(self):
        self.progress_data = {}
        self.lock = threading.Lock()
    
    def update_progress(self, video_id, status, progress=None):
        with self.lock:
            self.progress_data[video_id] = {
                'status': status,
                'progress': progress or "0%"
            }
    
    def get_all_progress(self):
        with self.lock:
            return self.progress_data.copy()

# Global progress tracker
if 'progress_tracker' not in st.session_state:
    st.session_state.progress_tracker = DownloadProgress()

def create_progress_hook(video_id, progress_tracker):
    """Create a progress hook for a specific video"""
    def progress_hook(d):
        if d['status'] == 'downloading':
            if '_percent_str' in d:
                percent = d['_percent_str'].strip()
                progress_tracker.update_progress(video_id, "⏳ Downloading", percent)
            elif 'downloaded_bytes' in d and 'total_bytes' in d:
                percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                progress_tracker.update_progress(video_id, "⏳ Downloading", f"{percent:.1f}%")
        elif d['status'] == 'finished':
            progress_tracker.update_progress(video_id, "✅ Complete", "100%")
    return progress_hook

def download_single_video(url, options, video_id, progress_tracker):
    """Download a single video"""
    try:
        progress_tracker.update_progress(video_id, "🔄 Starting", "0%")
        
        # Create options with progress hook
        download_options = options.copy()
        download_options['progress_hooks'] = [create_progress_hook(video_id, progress_tracker)]
        
        with yt_dlp.YoutubeDL(download_options) as ydl:
            # Get video info first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', f'Video_{video_id}')
            
            progress_tracker.update_progress(video_id, f"⏳ Downloading: {title[:30]}...", "0%")
            
            # Download the video
            ydl.download([url])
            
            return {
                'url': url,
                'title': title,
                'status': 'success',
                'message': '✅ Download completed successfully'
            }
            
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        progress_tracker.update_progress(video_id, error_msg, "Failed")
        return {
            'url': url,
            'title': f'Video_{video_id}',
            'status': 'error',
            'message': error_msg
        }

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
    
    # Show real-time progress
    progress_placeholder = st.empty()
    
    # Auto-refresh progress during downloads
    if st.session_state.is_downloading:
        progress_data = st.session_state.progress_tracker.get_all_progress()
        if progress_data:
            with progress_placeholder.container():
                for video_id, data in progress_data.items():
                    st.text(f"Video {video_id}: {data['status']}")
                    if data['progress'] != "Failed":
                        st.text(f"Progress: {data['progress']}")
                    st.divider()
        else:
            progress_placeholder.info("No downloads in progress")
        
        # Auto-refresh every 2 seconds during download
        time.sleep(0.1)
        st.rerun()
    else:
        # Show results from last download batch
        if st.session_state.download_results:
            with progress_placeholder.container():
                st.write("**Last Download Results:**")
                for result in st.session_state.download_results:
                    st.text(f"📹 {result['title'][:30]}...")
                    st.text(result['message'])
                    st.divider()
        else:
            progress_placeholder.info("No downloads completed yet")

# Download button and logic
st.subheader("🚀 Start Download")

download_button = st.button(
    "Start Batch Download", 
    type="primary", 
    disabled=not urls or st.session_state.is_downloading
)

if download_button:
    if not urls:
        st.error("Please enter at least one valid YouTube URL")
    else:
        # Set downloading state
        st.session_state.is_downloading = True
        st.session_state.download_results = []
        st.session_state.progress_tracker = DownloadProgress()
        
        # Configure yt-dlp options
        base_options = {
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'no_warnings': False,
            'extract_flat': False,
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
        
        # Start downloads using ThreadPoolExecutor
        def run_downloads():
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # Submit all download tasks
                future_to_url = {
                    executor.submit(
                        download_single_video, 
                        url, 
                        base_options.copy(), 
                        i+1, 
                        st.session_state.progress_tracker
                    ): url for i, url in enumerate(urls)
                }
                
                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_url):
                    result = future.result()
                    results.append(result)
            
            # Update session state with results
            st.session_state.download_results = results
            st.session_state.is_downloading = False
        
        # Run downloads in a separate thread to avoid blocking UI
        download_thread = threading.Thread(target=run_downloads)
        download_thread.start()
        
        st.info("🔄 Starting batch download... Progress will appear on the right.")
        st.rerun()

# Show download summary when downloads are complete
if st.session_state.download_results and not st.session_state.is_downloading:
    results = st.session_state.download_results
    completed = sum(1 for r in results if r['status'] == 'success')
    failed = sum(1 for r in results if r['status'] == 'error')
    
    if completed > 0:
        st.success(f"🎉 Batch download completed! {completed} successful, {failed} failed out of {len(results)} total")
    else:
        st.error(f"❌ All downloads failed. {failed} out of {len(results)} total")

# Instructions
st.subheader("📋 Instructions")
st.markdown("""
1. **Add URLs**: Paste YouTube URLs in the text area (one per line)
2. **Configure Options**: Choose download type, quality, and format in the sidebar
3. **Start Download**: Click the download button to begin batch processing
4. **Monitor Progress**: Watch the download status in real-time on the right
5. **Find Files**: Downloaded files will be saved in the `downloads` folder

**Supported URL formats:**
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://m.youtube.com/watch?v=VIDEO_ID`
""")


st.markdown("**Note**: Make sure you have `ffmpeg` installed for audio extraction features.")

# Footer
st.markdown("---")
st.markdown("Made with ❤️ using Streamlit and yt-dlp")
