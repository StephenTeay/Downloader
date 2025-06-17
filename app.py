import streamlit as st
from pytube import YouTube
from io import BytesIO
import re
import time

# NEW: URL sanitization function
def extract_video_id(url):
    # Extract YouTube video ID from various URL formats
    patterns = [
        r"youtube\.com/watch\?v=([^&]+)",
        r"youtu\.be/([^?]+)",
        r"youtube\.com/embed/([^?]+)",
        r"youtube\.com/v/([^?]+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

# Initialize session state
if 'download_history' not in st.session_state:
    st.session_state.download_history = []

def download_media(url, media_type='video'):
    """Download YouTube media and return as BytesIO object"""
    try:
        # NEW: Use video ID to create clean URL
        video_id = extract_video_id(url)
        if not video_id:
            raise ValueError("Invalid YouTube URL")
            
        clean_url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(clean_url)
        
        if media_type == 'audio':
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            filename = f"{yt.title}.mp3"
        else:
            stream = yt.streams.get_highest_resolution()
            filename = f"{yt.title}.mp4"
        
        buffer = BytesIO()
        stream.stream_to_buffer(buffer)
        buffer.seek(0)
        return buffer, filename, yt.title, clean_url, None
    except Exception as e:
        return None, None, None, url, str(e)

def sanitize_filename(filename):
    return "".join(c for c in filename if c.isalnum() or c in " -_.")

# Streamlit UI
st.title("🎬 YouTube Batch Downloader")
st.write("Download multiple YouTube videos or extract audio as MP3")

# Input section
with st.expander("📥 Input URLs", expanded=True):
    urls = st.text_area(
        "Enter YouTube URLs (one per line):", 
        height=150,
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/..."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        media_type = st.radio("Download Type:", ['Video', 'Audio'])
    with col2:
        batch_size = st.slider("Batch Size:", 1, 10, 3)

# Process URLs
if st.button("🚀 Download Media", use_container_width=True):
    if not urls.strip():
        st.warning("⚠️ Please enter at least one URL")
        st.stop()
    
    url_list = [url.strip() for url in urls.split('\n') if url.strip()]
    total_urls = len(url_list)
    media_type = media_type.lower()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    downloaded_items = []
    
    for i, url in enumerate(url_list[:batch_size]):
        try:
            progress = int((i + 1) / min(batch_size, total_urls) * 100)
            progress_bar.progress(min(progress, 100))
            status_text.text(f"📥 Processing item {i+1}/{min(batch_size, total_urls)}...")
            
            buffer, filename, title, clean_url, error = download_media(url, media_type)
            if error:
                raise Exception(error)
            
            clean_filename = sanitize_filename(filename)
            
            st.download_button(
                label=f"💾 Download: {title[:30]}..." if len(title) > 30 else f"💾 Download: {title}",
                data=buffer,
                file_name=clean_filename,
                mime='audio/mp3' if media_type == 'audio' else 'video/mp4',
                key=f"dl_{i}_{time.time()}"
            )
            
            st.session_state.download_history.insert(0, {
                'title': title,
                'original_url': url,
                'clean_url': clean_url,
                'type': media_type,
                'time': time.strftime("%Y-%m-%d %H:%M:%S")
            })
            downloaded_items.append(title)
            
        except Exception as e:
            st.error(f"❌ Failed to download: {str(e)}")
    
    if downloaded_items:
        status_text.success(f"✅ Successfully processed {len(downloaded_items)} items!")
        progress_bar.empty()

# Display download history
if st.session_state.download_history:
    with st.expander("📚 Download History"):
        for i, item in enumerate(st.session_state.download_history[:5]):
            st.caption(f"{i+1}. [{item['type'].upper()}] {item['time']}")
            st.markdown(f"**{item['title']}**")
            st.code(f"Original: {item['original_url']}\nCleaned: {item['clean_url']}")

# How to use section remains the same
