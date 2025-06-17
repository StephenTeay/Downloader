import streamlit as st
from pytube import YouTube
from io import BytesIO
import os
import time

# Initialize session state for download history
if 'download_history' not in st.session_state:
    st.session_state.download_history = []

def download_media(url, media_type='video'):
    """Download YouTube media and return as BytesIO object with filename"""
    try:
        yt = YouTube(url)
        if media_type == 'audio':
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            filename = f"{yt.title}.mp3"
        else:
            stream = yt.streams.get_highest_resolution()
            filename = f"{yt.title}.mp4"
        
        buffer = BytesIO()
        stream.stream_to_buffer(buffer)
        buffer.seek(0)
        return buffer, filename, yt.title, None
    except Exception as e:
        return None, None, None, str(e)

def sanitize_filename(filename):
    """Remove invalid characters from filenames"""
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
        batch_size = st.slider("Batch Size:", 1, 10, 3, 
                              help="Number of simultaneous downloads")

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
            # Update progress
            progress = int((i + 1) / min(batch_size, total_urls) * 100)
            progress_bar.progress(min(progress, 100))
            status_text.text(f"📥 Downloading item {i+1}/{min(batch_size, total_urls)}...")
            
            # Download media
            buffer, filename, title, error = download_media(url, media_type)
            if error:
                raise Exception(error)
            
            # Sanitize filename
            clean_filename = sanitize_filename(filename)
            
            # Create download button
            st.download_button(
                label=f"💾 Download: {title[:30]}...",
                data=buffer,
                file_name=clean_filename,
                mime='audio/mp3' if media_type == 'audio' else 'video/mp4',
                key=f"dl_{i}_{time.time()}"
            )
            
            # Add to history
            st.session_state.download_history.insert(0, {
                'title': title,
                'url': url,
                'type': media_type,
                'time': time.strftime("%Y-%m-%d %H:%M:%S")
            })
            downloaded_items.append(title)
            
        except Exception as e:
            st.error(f"❌ Failed to download {url}: {str(e)}")
    
    if downloaded_items:
        status_text.success(f"✅ Successfully downloaded {len(downloaded_items)} items!")
        progress_bar.empty()

# Display download history
if st.session_state.download_history:
    with st.expander("📚 Download History"):
        for i, item in enumerate(st.session_state.download_history[:5]):
            st.caption(f"{i+1}. [{item['type'].upper()}] {item['time']}")
            st.markdown(f"**{item['title']}**  \n`{item['url']}`")

# Add instructions
with st.expander("ℹ️ How to use"):
    st.markdown("""
    1. Paste YouTube URLs (one per line)
    2. Choose download type: Video or Audio
    3. Set batch size (number of simultaneous downloads)
    4. Click the 🚀 Download Media button
    5. Click individual download buttons for each item
    6. Access your download history below
    
    **Note:** 
    - For long videos, download might take 1-2 minutes
    - Batch size limited to 10 for performance
    - Audio files are saved as MP3 format
    - Special characters in titles are auto-removed
    """)

# Add footer
st.caption("Made with Streamlit and Pytube | Use for personal content only")
