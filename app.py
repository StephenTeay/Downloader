import streamlit as st
import yt_dlp
import os
from pathlib import Path
import concurrent.futures
import time
import queue
import threading
import zipfile
import tempfile
import io
import base64

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

# Create download directory in a temporary location
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "youtube_downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

st.info(f"📁 Files are temporarily stored on server at: `{DOWNLOAD_DIR}` and will be available for download below.")

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

# Global progress tracker (not in session state to avoid threading issues)
if 'progress_tracker_instance' not in st.session_state:
    st.session_state.progress_tracker_instance = None

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
    file_path = None
    title = f'Video_{video_id}'
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
            
            # Verify file was actually downloaded
            # yt-dlp might change the filename after post-processing (e.g., .mp4 to .mp3)
            # We need to find the actual file that was created.
            
            # Get expected output filename before post-processing
            expected_filename_base = ydl.prepare_filename(info)
            
            # Look for the file in the download directory, especially considering post-processing
            found_files = []
            for f in DOWNLOAD_DIR.iterdir():
                # Check if the filename starts with the expected base name
                # and if it has a common media extension
                if f.stem.startswith(Path(expected_filename_base).stem) and \
                   f.suffix.lower() in ['.mp4', '.mp3', '.m4a', '.webm', '.mkv', '.wav', '.flac']:
                    found_files.append(f)
            
            if found_files:
                # Assuming the most recently modified file among candidates is the one
                found_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                file_path = str(found_files[0])
                file_size = os.path.getsize(file_path)
                file_size_mb = file_size / (1024 * 1024)
                success_msg = f'✅ Downloaded successfully ({file_size_mb:.1f} MB)'
            else:
                success_msg = '⚠️ Download completed but file not found on disk'

        st.write(f"DEBUG: Download result for {title}: file_path={file_path}, message={success_msg}")
        
        return {
            'url': url,
            'title': title,
            'status': 'success' if file_path else 'warning', # Mark as warning if file not found after 'success'
            'message': success_msg,
            'file_path': file_path
        }
            
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        progress_tracker.update_progress(video_id, error_msg, "Failed")
        st.error(f"DEBUG: Error downloading {url}: {e}")
        return {
            'url': url,
            'title': title,
            'status': 'error',
            'message': error_msg,
            'file_path': None
        }

def create_download_button(file_path, file_name):
    """Create a download button for a file"""
    st.write(f"DEBUG: Attempting to create button for: {file_path}, exists: {os.path.exists(file_path)}")
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        st.download_button(
            label=f"⬇️ Download {file_name}",
            data=file_data,
            file_name=file_name,
            mime="application/octet-stream"
        )
        return True
    return False

def create_zip_download(files_list):
    """Create a zip file containing all downloaded files"""
    if not files_list:
        return None
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in files_list:
            if os.path.exists(file_path):
                file_name = os.path.basename(file_path)
                zip_file.write(file_path, file_name)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def validate_youtube_url(url):
    """Validate if URL is a valid YouTube URL (improved check)"""
    youtube_patterns = [
        'youtube.com/watch?v=',
        'youtu.be/',
        'youtube.com/playlist?list=',
        'youtube.com/shorts/'
    ]
    return any(pattern in url for pattern in youtube_patterns)

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
        placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ\nhttps://youtu.be/another_video_id",
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
    if st.session_state.is_downloading: # Removed the unnecessary check for progress_tracker_instance here
        if st.session_state.progress_tracker_instance:
            progress_data = st.session_state.progress_tracker_instance.get_all_progress()
            if progress_data:
                with progress_placeholder.container():
                    for video_id, data in progress_data.items():
                        st.text(f"Video {video_id}: {data['status']}")
                        if data['progress'] != "Failed":
                            st.text(f"Progress: {data['progress']}")
                        st.divider()
            else:
                progress_placeholder.info("No downloads in progress (Progress data not yet available).")
        else:
             progress_placeholder.info("Initializing download tracker...")
        
        # Auto-refresh every 0.5 seconds during download
        time.sleep(0.5)
        st.rerun() # This will cause the page to re-run and update progress
    else:
        # Show results from last download batch
        if st.session_state.download_results:
            with progress_placeholder.container():
                st.write("**Last Download Results:**")
                for result in st.session_state.download_results:
                    st.text(f"📹 {result['title'][:40]}...")
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
        
        # Create a new progress tracker instance
        progress_tracker = DownloadProgress()
        st.session_state.progress_tracker_instance = progress_tracker
        
        # Configure yt-dlp options
        base_options = {
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'no_warnings': True, # Suppress warnings for cleaner output
            'extract_flat': False,
            'writeinfojson': False,  # Don't write info json
            'writethumbnail': False,  # Don't write thumbnail
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
                format_string = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' # Prefer mp4 if possible
            elif quality == "worst":
                format_string = 'worst'
            else:
                format_string = f'bestvideo[height<={quality[:-1]}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality[:-1]}]'
            
            if format_selection != "any":
                # Ensure the format_string handles cases like 'mp4'
                if format_selection == 'mp4':
                     format_string = f'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
                else:
                    format_string = f'{format_string}[ext={format_selection}]'
            
            base_options['format'] = format_string
            base_options['merge_output_format'] = format_selection if format_selection != "any" else "mp4" # Ensure merged output is preferred format

        st.write(f"DEBUG: yt-dlp options: {base_options}")
        
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
                        progress_tracker  # Pass the local instance
                    ): url for i, url in enumerate(urls)
                }
                
                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_url):
                    result = future.result()
                    results.append(result)
            
            # Update session state with results
            st.session_state.download_results = results
            st.session_state.is_downloading = False
            # Trigger a rerun after downloads complete to show final results and buttons
            st.rerun() 
        
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
        
        # Show file listing with download buttons
        if DOWNLOAD_DIR.exists():
            files = list(DOWNLOAD_DIR.glob('*'))
            video_files = [f for f in files if f.is_file() and f.suffix.lower() in ['.mp4', '.mp3', '.m4a', '.webm', '.mkv', '.wav', '.flac']]
            st.write(f"DEBUG: Files found in DOWNLOAD_DIR after completion: {[f.name for f in files]}")
            st.write(f"DEBUG: Filtered video_files after completion: {[f.name for f in video_files]}")
            
            if video_files:
                st.subheader("📂 Your Downloaded Files (From Latest Batch)")
                
                # Create zip download for all files
                if len(video_files) > 1:
                    zip_data = create_zip_download([str(f) for f in video_files])
                    if zip_data:
                        st.download_button(
                            label="📦 Download All Files as ZIP",
                            data=zip_data,
                            file_name="youtube_downloads.zip",
                            mime="application/zip",
                            key="batch_zip_download" # Unique key
                        )
                        st.divider()
                
                # Individual file downloads
                for file in sorted(video_files, key=lambda x: x.stat().st_mtime, reverse=True):
                    file_size = file.stat().st_size / (1024 * 1024)  # MB
                    col1_d, col2_d = st.columns([3, 1])
                    
                    with col1_d:
                        st.text(f"📄 {file.name} ({file_size:.1f} MB)")
                    
                    with col2_d:
                        create_download_button(str(file), file.name)
            else:
                st.info("No new media files were found in the download directory from this batch.")
    else:
        st.error(f"❌ All downloads failed. {failed} out of {len(results)} total. Check the 'Last Download Results' above for details.")

# Add file browser section with download buttons
st.subheader("📂 All Available Downloads on Server")
if DOWNLOAD_DIR.exists():
    files = list(DOWNLOAD_DIR.glob('*'))
    video_files = [f for f in files if f.is_file() and f.suffix.lower() in ['.mp4', '.mp3', '.m4a', '.webm', '.mkv', '.wav', '.flac']]
    
    st.write(f"DEBUG: All files found in DOWNLOAD_DIR: {[f.name for f in files]}")
    st.write(f"DEBUG: All filtered video_files: {[f.name for f in video_files]}")
    
    if video_files:
        st.write(f"**Files ready for download:** ({len(video_files)} files)")
        
        # Bulk download option
        if len(video_files) > 1:
            zip_data = create_zip_download([str(f) for f in video_files])
            if zip_data:
                st.download_button(
                    label="📦 Download All Files as ZIP",
                    data=zip_data,
                    file_name="youtube_downloads.zip",
                    mime="application/zip",
                    key="bulk_download_all" # Unique key
                )
                st.divider()
        
        # Individual downloads
        for file in sorted(video_files, key=lambda x: x.stat().st_mtime, reverse=True):
            file_size = file.stat().st_size / (1024 * 1024)  # MB
            modified_time = time.ctime(file.stat().st_mtime)
            
            col1_f, col2_f = st.columns([3, 1])
            with col1_f:
                st.text(f"📄 {file.name}")
                st.caption(f"Size: {file_size:.1f} MB | Modified: {modified_time}")
            
            with col2_f:
                create_download_button(str(file), file.name)
    else:
        st.info("No video/audio files available for download yet in the temporary directory.")
        
        # Clean up any non-media files
        other_files = [f for f in files if f.is_file() and f.suffix.lower() not in ['.mp4', '.mp3', '.m4a', '.webm', '.mkv', '.wav', '.flac']]
        if other_files:
            st.caption(f"Note: Found {len(other_files)} other files (e.g., info/thumbnails) - only media files are shown. You can manually delete these from the server if needed.")
else:
    st.error("Download folder not accessible or does not exist!")

# Instructions
st.subheader("📋 Instructions")
st.markdown("""
1.  **Add URLs**: Paste YouTube URLs in the text area (one per line).
2.  **Configure Options**: Choose download type, quality, and format in the sidebar.
3.  **Start Download**: Click the download button to begin batch processing.
4.  **Monitor Progress**: Watch the download status in real-time on the right.
5.  **Download Files**: Use the download buttons below to save files to your device.
6.  **Bulk Download**: Use "Download All as ZIP" for multiple files at once.

**Supported URL formats:**
-   `https://www.youtube.com/watch?v=VIDEO_ID`
-   `https://youtu.be/VIDEO_ID`
-   `https://www.youtube.com/playlist?list=PLAYLIST_ID` (downloads videos from playlist)
-   `https://www.youtube.com/shorts/SHORT_ID`
""")

# Requirements info
st.subheader("🔧 Installation Requirements")
st.code("""
pip install streamlit yt-dlp
""")

st.markdown("**Note**: Make sure you have `ffmpeg` installed on the system running this Streamlit app for audio extraction and format conversion features. Streamlit Cloud usually has `ffmpeg` pre-installed.")

# Footer
st.markdown("---")
st.markdown("Made with ❤️ using Streamlit and yt-dlp")
