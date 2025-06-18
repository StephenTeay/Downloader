import streamlit as st
import yt_dlp
import os
import threading
import time
from pathlib import Path
import zipfile
from datetime import datetime
import tempfile
import shutil

# Page configuration
st.set_page_config(
    page_title="YouTube Downloader",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'downloads' not in st.session_state:
    st.session_state.downloads = []
if 'download_status' not in st.session_state:
    st.session_state.download_status = {}
if 'download_progress' not in st.session_state:
    st.session_state.download_progress = {}
if 'completed_files' not in st.session_state:
    st.session_state.completed_files = []

class StreamlitProgressHook:
    def __init__(self, video_id, status_placeholder, progress_bar):
        self.video_id = video_id
        self.status_placeholder = status_placeholder
        self.progress_bar = progress_bar
        
    def __call__(self, d):
        if d['status'] == 'downloading':
            if 'total_bytes' in d and d['total_bytes']:
                percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                self.progress_bar.progress(percent / 100)
                speed = d.get('_speed_str', 'N/A')
                self.status_placeholder.info(f"Downloading... {percent:.1f}% ({speed})")
                st.session_state.download_progress[self.video_id] = percent
            elif '_percent_str' in d:
                # Fallback for when total_bytes is not available
                percent_str = d['_percent_str'].strip('%')
                try:
                    percent = float(percent_str)
                    self.progress_bar.progress(percent / 100)
                    speed = d.get('_speed_str', 'N/A')
                    self.status_placeholder.info(f"Downloading... {percent:.1f}% ({speed})")
                    st.session_state.download_progress[self.video_id] = percent
                except ValueError:
                    pass
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            filename = os.path.basename(d['filename'])
            self.status_placeholder.success(f"✅ Download completed: {filename}")
            st.session_state.download_status[self.video_id] = 'completed'
            st.session_state.completed_files.append(d['filename'])
        elif d['status'] == 'error':
            self.status_placeholder.error(f"❌ Error: {d.get('error', 'Unknown error')}")
            st.session_state.download_status[self.video_id] = 'error'

def get_video_info(url):
    """Get video information without downloading"""
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail', ''),
                'description': info.get('description', '')[:200] + '...' if info.get('description') else ''
            }
    except Exception as e:
        return {'error': str(e)}

def download_video(url, options, video_id, status_placeholder, progress_bar):
    """Download a single video"""
    try:
        st.session_state.download_status[video_id] = 'downloading'
        
        # Create progress hook
        progress_hook = StreamlitProgressHook(video_id, status_placeholder, progress_bar)
        options['progress_hooks'] = [progress_hook]
        
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
            
    except Exception as e:
        status_placeholder.error(f"❌ Error: {str(e)}")
        st.session_state.download_status[video_id] = 'error'

def create_download_options(download_dir, quality, format_type, audio_only):
    """Create yt-dlp options based on user selection"""
    opts = {
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
    }
    
    # Handle FFmpeg path for Streamlit Cloud
    import shutil
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        opts['ffmpeg_location'] = ffmpeg_path
    elif audio_only:
        # Fallback: download best audio format without conversion
        st.warning("FFmpeg not found. Downloading in original audio format.")
        opts['format'] = 'bestaudio/best'
        return opts
    
    if audio_only:
        if format_type == "mp3":
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif format_type == "m4a":
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }]
        elif format_type == "wav":
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }]
    else:
        if quality == "Best":
            opts['format'] = 'best'
        elif quality == "Worst":
            opts['format'] = 'worst'
        else:
            height = quality.replace('p', '')
            opts['format'] = f'best[height<={height}]'
    
    return opts

def create_zip_download(files):
    """Create a ZIP file containing all downloaded files"""
    if not files:
        return None
    
    # Create temporary zip file
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, f"youtube_downloads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file_path in files:
            if os.path.exists(file_path):
                # Add file to zip with just the filename (not full path)
                zipf.write(file_path, os.path.basename(file_path))
    
    return zip_path

# Main app
def main():
    st.title("📺 Multi-threaded YouTube Downloader")
    st.markdown("Download multiple YouTube videos simultaneously with audio extraction support")
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Download Settings")
        
        # Quality selection
        quality = st.selectbox(
            "Video Quality",
            ["Best", "720p", "480p", "360p", "240p", "Worst"],
            index=0
        )
        
        # Audio only toggle
        audio_only = st.checkbox("Audio Only", value=False)
        
        # Add warning for cloud deployment
        if audio_only:
            st.warning("⚠️ Audio extraction requires FFmpeg. If deployed on Streamlit Cloud, ensure packages.txt includes 'ffmpeg'")
        
        # Format selection
        if audio_only:
            format_type = st.selectbox(
                "Audio Format",
                ["mp3", "m4a", "wav"],
                index=0
            )
        else:
            format_type = st.selectbox(
                "Video Format",
                ["mp4", "webm"],
                index=0
            )
        
        # Max concurrent downloads
        max_concurrent = st.slider(
            "Max Concurrent Downloads",
            min_value=1,
            max_value=10,
            value=3,
            help="Number of videos to download simultaneously"
        )
        
        st.markdown("---")
        st.markdown("### 📁 Download Location")
        st.info("Files will be saved to a temporary directory and can be downloaded as a ZIP file.")
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("🔗 YouTube URLs")
        urls_input = st.text_area(
            "Enter YouTube URLs (one per line)",
            height=150,
            placeholder="https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...",
            help="Paste YouTube video URLs, one per line"
        )
        
        # Parse URLs
        urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
        
        if urls:
            st.success(f"Found {len(urls)} URL(s)")
            
            # Preview videos button
            if st.button("🔍 Preview Videos", type="secondary"):
                with st.expander("Video Previews", expanded=True):
                    for i, url in enumerate(urls):
                        with st.spinner(f"Loading info for video {i+1}..."):
                            info = get_video_info(url)
                            
                            if 'error' in info:
                                st.error(f"❌ Error loading video {i+1}: {info['error']}")
                            else:
                                col_thumb, col_info = st.columns([1, 3])
                                
                                with col_thumb:
                                    if info['thumbnail']:
                                        st.image(info['thumbnail'], width=120)
                                
                                with col_info:
                                    st.write(f"**{info['title']}**")
                                    st.write(f"👤 {info['uploader']}")
                                    if info['duration']:
                                        minutes = info['duration'] // 60
                                        seconds = info['duration'] % 60
                                        st.write(f"⏱️ {minutes}:{seconds:02d}")
                                    if info['view_count']:
                                        st.write(f"👀 {info['view_count']:,} views")
                                
                                st.markdown("---")
    
    with col2:
        st.header("📊 Download Status")
        
        if urls and st.button("🚀 Start Downloads", type="primary", use_container_width=True):
            # Create temporary download directory
            download_dir = tempfile.mkdtemp()
            
            # Clear previous state
            st.session_state.downloads = []
            st.session_state.download_status = {}
            st.session_state.download_progress = {}
            st.session_state.completed_files = []
            
            # Create download options
            options = create_download_options(download_dir, quality, format_type, audio_only)
            
            st.success("Downloads started!")
            
            # Create download containers
            download_containers = []
            for i, url in enumerate(urls):
                video_id = f"video_{i}"
                container = st.container()
                with container:
                    st.write(f"**Video {i+1}**: {url[:50]}...")
                    progress_bar = st.progress(0)
                    status_placeholder = st.empty()
                    status_placeholder.info("⏳ Queued...")
                
                download_containers.append((video_id, url, status_placeholder, progress_bar))
            
            # Start downloads with threading
            def start_download_thread(video_id, url, status_placeholder, progress_bar):
                download_video(url, options.copy(), video_id, status_placeholder, progress_bar)
            
            # Limit concurrent downloads
            active_threads = []
            for video_id, url, status_placeholder, progress_bar in download_containers:
                # Wait if we have too many active downloads
                while len([t for t in active_threads if t.is_alive()]) >= max_concurrent:
                    time.sleep(0.1)
                
                # Start new download thread
                thread = threading.Thread(
                    target=start_download_thread,
                    args=(video_id, url, status_placeholder, progress_bar),
                    daemon=True
                )
                thread.start()
                active_threads.append(thread)
                time.sleep(0.5)  # Small delay between starts
            
            # Show overall progress
            st.markdown("---")
            overall_progress = st.progress(0)
            overall_status = st.empty()
            
            # Monitor progress
            while True:
                completed = len([s for s in st.session_state.download_status.values() if s in ['completed', 'error']])
                total = len(urls)
                
                if completed > 0:
                    progress = completed / total
                    overall_progress.progress(progress)
                    overall_status.info(f"Overall Progress: {completed}/{total} completed")
                
                if completed == total:
                    break
                
                time.sleep(1)
            
            # Create download ZIP when all complete
            if st.session_state.completed_files:
                zip_path = create_zip_download(st.session_state.completed_files)
                if zip_path:
                    with open(zip_path, "rb") as fp:
                        st.download_button(
                            label="📦 Download All Files (ZIP)",
                            data=fp.read(),
                            file_name=os.path.basename(zip_path),
                            mime="application/zip",
                            type="primary",
                            use_container_width=True
                        )
                    st.success("✅ All downloads completed! Click the button above to download your files.")
        
        # Clear button
        if st.button("🗑️ Clear URLs", use_container_width=True):
            st.rerun()
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
            <p>Built with Streamlit • Powered by yt-dlp</p>
            <p><small>⚠️ Please respect copyright laws and YouTube's Terms of Service</small></p>
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
