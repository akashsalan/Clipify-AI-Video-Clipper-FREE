/**
 * Clipify AI - Live Studio Frontend Controller
 */
(function() {
  'use strict';

  let pollInterval = null;
  let currentSourceType = 'youtube';
  let isSessionActive = false;

  // DOM Elements
  const sourceTabs = document.querySelectorAll('.source-tab');
  const liveSourceUrl = document.getElementById('liveSourceUrl');
  const btnConnectStream = document.getElementById('btnConnectStream');
  const btnDisconnectStream = document.getElementById('btnDisconnectStream');
  const btnInstantClip = document.getElementById('btnInstantClip');
  const streamLiveBadge = document.getElementById('streamLiveBadge');
  const streamLiveText = document.getElementById('streamLiveText');
  const monitorTitle = document.getElementById('monitorTitle');
  const streamAuthor = document.getElementById('streamAuthor');
  const telemetryElapsed = document.getElementById('telemetryElapsed');
  const telemetryBuffer = document.getElementById('telemetryBuffer');
  const telemetryChunks = document.getElementById('telemetryChunks');
  const monitorPlaceholder = document.getElementById('monitorPlaceholder');
  const monitorActiveView = document.getElementById('monitorActiveView');
  const transcriptFeed = document.getElementById('transcriptFeed');
  const liveClipsGrid = document.getElementById('liveClipsGrid');
  const emptyClipsMsg = document.getElementById('emptyClipsMsg');
  const clipsCount = document.getElementById('clipsCount');
  const obsConfigBox = document.getElementById('obsConfigBox');
  const youtubeInputGroup = document.getElementById('youtubeInputGroup');
  const sensitivitySlider = document.getElementById('sensitivitySlider');
  const sensitivityOut = document.getElementById('sensitivityOut');
  const toggleAutoClip = document.getElementById('toggleAutoClip');
  const bufferWindowSelect = document.getElementById('bufferWindowSelect');
  const liveModelSelect = document.getElementById('liveModelSelect');

  // Modal elements
  const clipPreviewModal = document.getElementById('clipPreviewModal');
  const modalClipTitle = document.getElementById('modalClipTitle');
  const modalVideoPlayer = document.getElementById('modalVideoPlayer');
  const modalDownloadBtn = document.getElementById('modalDownloadBtn');
  const modalDownloadOrigBtn = document.getElementById('modalDownloadOrigBtn');
  const closeClipModal = document.getElementById('closeClipModal');

  function init() {
    setupTabs();
    setupActions();
    setupSensitivity();
    setupModal();
    setupCopyButtons();
    startPolling();
  }

  function setupTabs() {
    sourceTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        sourceTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentSourceType = tab.dataset.source;

        if (currentSourceType === 'obs') {
          obsConfigBox.style.display = 'block';
          youtubeInputGroup.style.display = 'none';
        } else {
          obsConfigBox.style.display = 'none';
          youtubeInputGroup.style.display = 'block';
          if (currentSourceType === 'youtube') {
            liveSourceUrl.placeholder = 'https://www.youtube.com/watch?v=... or https://www.youtube.com/live/...';
          } else if (currentSourceType === 'tiktok') {
            liveSourceUrl.placeholder = 'https://www.tiktok.com/@username/live';
          }
        }
      });
    });
  }

  function setupSensitivity() {
    if (sensitivitySlider && sensitivityOut) {
      sensitivitySlider.addEventListener('input', (e) => {
        const val = parseInt(e.target.value, 10);
        let label = 'Balanced';
        if (val <= 3) label = 'Conservative';
        else if (val >= 8) label = 'High Frequency';
        sensitivityOut.textContent = `${val} (${label})`;
      });
    }
  }

  function setupCopyButtons() {
    document.querySelectorAll('.copy-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetId = btn.dataset.target;
        const input = document.getElementById(targetId);
        if (input) {
          input.select();
          navigator.clipboard.writeText(input.value);
          const orig = btn.textContent;
          btn.textContent = 'Copied!';
          setTimeout(() => { btn.textContent = orig; }, 1500);
        }
      });
    });

    const btnObsGuide = document.getElementById('btnObsGuide');
    if (btnObsGuide) {
      btnObsGuide.addEventListener('click', () => {
        const obsTab = document.querySelector('.source-tab[data-source="obs"]');
        if (obsTab) obsTab.click();
      });
    }
  }

  function setupActions() {
    btnConnectStream.addEventListener('click', async () => {
      btnConnectStream.disabled = true;
      btnConnectStream.textContent = 'Connecting...';

      let sourceUrl = liveSourceUrl.value.trim();
      if (currentSourceType === 'obs' && !sourceUrl) {
        sourceUrl = 'rtmp://127.0.0.1:1935/live/stream';
      }

      try {
        const resp = await fetch('/api/live/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_type: currentSourceType,
            source_url: sourceUrl,
            auto_clip: toggleAutoClip ? toggleAutoClip.checked : true,
            sensitivity: sensitivitySlider ? parseInt(sensitivitySlider.value, 10) : 5,
            buffer_minutes: bufferWindowSelect ? parseInt(bufferWindowSelect.value, 10) : 10,
            model_name: liveModelSelect ? liveModelSelect.value : 'qwen2.5:3b',
          }),
        });

        const data = await resp.json();
        if (!resp.ok) {
          alert('Failed to connect: ' + (data.error || 'Unknown error'));
          btnConnectStream.disabled = false;
          btnConnectStream.textContent = 'Connect & Start Clipping';
          return;
        }

        updateUIStatus(data.status);
      } catch (err) {
        alert('Connection error: ' + err.message);
        btnConnectStream.disabled = false;
        btnConnectStream.textContent = 'Connect & Start Clipping';
      }
    });

    btnDisconnectStream.addEventListener('click', async () => {
      btnDisconnectStream.disabled = true;
      try {
        await fetch('/api/live/disconnect', { method: 'POST' });
        fetchStatus();
      } catch (err) {
        console.error('Disconnect error:', err);
      } finally {
        btnDisconnectStream.disabled = false;
      }
    });

    btnInstantClip.addEventListener('click', async () => {
      btnInstantClip.disabled = true;
      const originalText = btnInstantClip.textContent;
      btnInstantClip.textContent = 'Generating 30s Short...';

      try {
        const resp = await fetch('/api/live/instant-clip', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ duration: 30 }),
        });
        const data = await resp.json();
        if (resp.ok && data.clip) {
          fetchClips();
        } else {
          alert(data.error || 'Could not generate instant clip.');
        }
      } catch (err) {
        alert('Instant clip error: ' + err.message);
      } finally {
        btnInstantClip.disabled = false;
        btnInstantClip.textContent = originalText;
      }
    });

    const btnRefreshClips = document.getElementById('btnRefreshClips');
    if (btnRefreshClips) {
      btnRefreshClips.addEventListener('click', fetchClips);
    }
  }

  function setupModal() {
    closeClipModal.addEventListener('click', () => {
      modalVideoPlayer.pause();
      modalVideoPlayer.src = '';
      clipPreviewModal.style.display = 'none';
    });

    clipPreviewModal.addEventListener('click', (e) => {
      if (e.target === clipPreviewModal) {
        modalVideoPlayer.pause();
        modalVideoPlayer.src = '';
        clipPreviewModal.style.display = 'none';
      }
    });
  }

  function startPolling() {
    fetchStatus();
    fetchClips();
    fetchTranscripts();

    pollInterval = setInterval(() => {
      fetchStatus();
      if (isSessionActive) {
        fetchTranscripts();
        fetchClips();
      }
    }, 1500);
  }

  async function fetchStatus() {
    try {
      const resp = await fetch('/api/live/status');
      if (!resp.ok) return;
      const data = await resp.json();
      updateUIStatus(data);
    } catch (err) {
      console.debug('Status fetch error:', err);
    }
  }

  function updateUIStatus(statusData) {
    if (!statusData) return;
    isSessionActive = Boolean(statusData.session_active);

    // Live Badge & Actions
    if (isSessionActive) {
      streamLiveBadge.className = 'live-badge active';
      streamLiveText.textContent = statusData.status.toUpperCase();
      btnConnectStream.style.display = 'none';
      btnDisconnectStream.style.display = 'inline-flex';
      btnInstantClip.disabled = false;
      monitorPlaceholder.style.display = 'none';
      monitorActiveView.style.display = 'flex';
    } else {
      streamLiveBadge.className = 'live-badge';
      streamLiveText.textContent = 'IDLE';
      btnConnectStream.style.display = 'inline-flex';
      btnConnectStream.disabled = false;
      btnConnectStream.textContent = 'Connect & Start Clipping';
      btnDisconnectStream.style.display = 'none';
      btnInstantClip.disabled = true;
      monitorPlaceholder.style.display = 'flex';
      monitorActiveView.style.display = 'none';
    }

    // Telemetry
    if (statusData.elapsed_seconds) {
      telemetryElapsed.textContent = formatDuration(statusData.elapsed_seconds);
    } else {
      telemetryElapsed.textContent = '00:00:00';
    }

    telemetryBuffer.textContent = `Buffer: ${Math.round(statusData.buffer_duration_seconds || 0)}s`;
    telemetryChunks.textContent = `${statusData.buffer_chunks || 0} chunks`;

    // Metadata
    if (statusData.metadata && statusData.metadata.title) {
      monitorTitle.textContent = statusData.metadata.title;
      if (statusData.metadata.author) {
        streamAuthor.textContent = statusData.metadata.author;
      }
    }
  }

  async function fetchTranscripts() {
    try {
      const resp = await fetch('/api/live/transcript');
      if (!resp.ok) return;
      const data = await resp.json();
      const segments = data.segments || [];

      if (segments.length === 0) {
        if (!isSessionActive) {
          transcriptFeed.innerHTML = '<div class="empty-feed">Speech will transcribe here in real-time as the stream plays...</div>';
        }
        return;
      }

      transcriptFeed.innerHTML = '';
      segments.slice(-20).forEach(seg => {
        const item = document.createElement('div');
        item.className = 'transcript-item';
        item.innerHTML = `
          <span class="transcript-time">${formatDuration(seg.start)}</span>
          <p class="transcript-text">${escapeHtml(seg.text)}</p>
        `;
        transcriptFeed.appendChild(item);
      });

      // Smooth scroll to bottom
      transcriptFeed.scrollTop = transcriptFeed.scrollHeight;
    } catch (err) {
      console.debug('Transcript error:', err);
    }
  }

  async function fetchClips() {
    try {
      const resp = await fetch('/api/live/clips');
      if (!resp.ok) return;
      const data = await resp.json();
      const clips = data.clips || [];

      clipsCount.textContent = clips.length;

      if (clips.length === 0) {
        emptyClipsMsg.style.display = 'flex';
        return;
      }

      emptyClipsMsg.style.display = 'none';
      liveClipsGrid.innerHTML = '';

      clips.forEach(clip => {
        const card = document.createElement('div');
        card.className = 'live-clip-card';
        card.innerHTML = `
          <div class="clip-thumb-box">
            <img src="${clip.thumbnail}" alt="" class="clip-thumb" onerror="this.src='/static/icon.png'">
            <span class="clip-badge">${escapeHtml(clip.category || 'Highlight')}</span>
            <span class="clip-duration">${clip.duration}s</span>
            <button type="button" class="play-overlay-btn" title="Preview Short">▶</button>
          </div>
          <div class="clip-details">
            <h4 class="clip-title">${escapeHtml(clip.title)}</h4>
            <div class="clip-meta">
              <span>${clip.formatted_time || ''}</span>
              <span>${clip.duration}s</span>
            </div>
            <div class="clip-actions">
              <a href="${clip.vertical_video}" download="${escapeHtml(clip.title)}.mp4" class="primary mini-btn">Download 9:16 ↓</a>
              <button type="button" class="ghost mini-btn delete-clip-btn" data-id="${clip.id}">✕</button>
            </div>
          </div>
        `;

        // Card play preview
        card.querySelector('.play-overlay-btn').addEventListener('click', () => {
          openPreviewModal(clip);
        });

        // Delete button
        card.querySelector('.delete-clip-btn').addEventListener('click', async (e) => {
          e.stopPropagation();
          if (confirm('Delete this generated clip?')) {
            await fetch(`/api/live/clips/${clip.id}`, { method: 'DELETE' });
            fetchClips();
          }
        });

        liveClipsGrid.appendChild(card);
      });
    } catch (err) {
      console.debug('Clips fetch error:', err);
    }
  }

  function openPreviewModal(clip) {
    modalClipTitle.textContent = clip.title;
    modalVideoPlayer.src = clip.vertical_video;
    modalDownloadBtn.href = clip.vertical_video;
    modalDownloadBtn.download = `${clip.title}_9_16.mp4`;

    if (clip.original_video) {
      modalDownloadOrigBtn.href = clip.original_video;
      modalDownloadOrigBtn.download = `${clip.title}_16_9.mp4`;
      modalDownloadOrigBtn.style.display = 'inline-flex';
    } else {
      modalDownloadOrigBtn.style.display = 'none';
    }

    clipPreviewModal.style.display = 'flex';
    modalVideoPlayer.play().catch(() => {});
  }

  function formatDuration(sec) {
    const s = Math.floor(sec || 0);
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  document.addEventListener('DOMContentLoaded', init);
})();
