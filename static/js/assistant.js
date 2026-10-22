/**
 * Annam Loop Voice Assistant Client
 * Implements Web Speech API (speech-to-text), SpeechSynthesis (text-to-speech),
 * and connects to Flask /api/assistant calling MCP server over Streamable HTTP.
 */

document.addEventListener('DOMContentLoaded', () => {
  const micBtn = document.getElementById('micBtn');
  const micStatusText = document.getElementById('micStatusText');
  const langSelect = document.getElementById('langSelect');
  const muteBtn = document.getElementById('muteBtn');
  const transcriptInput = document.getElementById('transcriptInput');
  const sendBtn = document.getElementById('sendBtn');
  const chatThread = document.getElementById('chatThread');

  let isListening = false;
  let isMuted = false;
  let recognition = null;

  // Check Web Speech API support
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = langSelect.value;

    recognition.onstart = () => {
      isListening = true;
      micBtn.classList.add('listening');
      micStatusText.textContent = "Listening... Speak now";
    };

    recognition.onresult = (event) => {
      let currentTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        currentTranscript += event.results[i][0].transcript;
      }
      transcriptInput.value = currentTranscript;
    };

    recognition.onerror = (event) => {
      console.warn("Speech recognition error:", event.error);
      stopListening();
      if (event.error === 'not-allowed') {
        micStatusText.textContent = "Microphone access blocked. You can type below.";
      } else {
        micStatusText.textContent = `Speech error (${event.error}). Click to retry or type below.`;
      }
    };

    recognition.onend = () => {
      stopListening();
      const val = transcriptInput.value.trim();
      if (val) {
        handleUserMessage(val);
      }
    };
  } else {
    micStatusText.textContent = "Voice input unsupported in this browser. Type your request below.";
  }

  function startListening() {
    if (!recognition) {
      alert("Web Speech API is not supported in this browser. Please type your message.");
      return;
    }
    try {
      window.speechSynthesis.cancel();
      recognition.lang = langSelect.value;
      transcriptInput.value = '';
      recognition.start();
    } catch (e) {
      console.error(e);
      stopListening();
    }
  }

  function stopListening() {
    isListening = false;
    micBtn.classList.remove('listening');
    micStatusText.textContent = "Click microphone to speak";
    try {
      if (recognition) recognition.stop();
    } catch (e) {}
  }

  // Mic click handler
  micBtn.addEventListener('click', () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  });

  // Mute button handler
  muteBtn.addEventListener('click', () => {
    isMuted = !isMuted;
    if (isMuted) {
      muteBtn.classList.add('active');
      muteBtn.textContent = "🔇 Muted";
      window.speechSynthesis.cancel();
    } else {
      muteBtn.classList.remove('active');
      muteBtn.textContent = "🔊 Sound On";
    }
  });

  // Send button handler
  sendBtn.addEventListener('click', () => {
    const text = transcriptInput.value.trim();
    if (text) {
      handleUserMessage(text);
    }
  });

  transcriptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const text = transcriptInput.value.trim();
      if (text) {
        handleUserMessage(text);
      }
    }
  });

  // Global helper for prompt pills
  window.sendQuickPrompt = (text) => {
    transcriptInput.value = text;
    handleUserMessage(text);
  };

  // Main message processing function
  async function handleUserMessage(text) {
    appendUserBubble(text);
    transcriptInput.value = '';

    const role = document.querySelector('.role-select')?.value || 'customer';

    // Show temporary thinking indicator
    const thinkingId = 'thinking-' + Date.now();
    appendAssistantBubble("⏳ Thinking & contacting MCP server...", null, null, null, thinkingId);

    try {
      const resp = await fetch('/api/assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: text, role: role })
      });

      const data = await resp.json();
      removeBubble(thinkingId);

      // Render assistant response with tool panel and interactive result cards
      appendAssistantBubble(data.reply_text, data.tool_name, data.tool_args, data.tool_result);

      // Read reply aloud
      speakReply(data.reply_text);
    } catch (err) {
      removeBubble(thinkingId);
      appendAssistantBubble("Sorry, failed to reach the server. Please ensure the MCP server is running on port 8000.", null, null, null);
    }
  }

  function appendUserBubble(text) {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user';
    bubble.textContent = text;
    chatThread.appendChild(bubble);
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  function appendAssistantBubble(replyText, toolName, toolArgs, toolResult, customId = null) {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble assistant';
    if (customId) bubble.id = customId;

    // Spoken reply text
    const spokenDiv = document.createElement('div');
    spokenDiv.className = 'assistant-spoken';
    spokenDiv.innerHTML = `<span>🤖</span> <span>${escapeHtml(replyText)}</span>`;
    bubble.appendChild(spokenDiv);

    // If an MCP tool was called, render collapsible monospace Tool Called Panel
    if (toolName) {
      const toolPanel = document.createElement('div');
      toolPanel.className = 'tool-panel';

      const panelHeader = document.createElement('div');
      panelHeader.className = 'tool-header';
      panelHeader.innerHTML = `
        <span>⚡ MCP Tool Executed: <span class="tool-name-badge">${escapeHtml(toolName)}()</span></span>
        <span style="font-size:0.75rem; text-decoration: underline;">toggle JSON</span>
      `;

      const panelBody = document.createElement('div');
      panelBody.className = 'tool-body';
      panelBody.innerHTML = `
        <pre><strong>Arguments:</strong>\n${escapeHtml(JSON.stringify(toolArgs, null, 2))}\n\n<strong>MCP Result:</strong>\n${escapeHtml(JSON.stringify(toolResult, null, 2))}</pre>
      `;

      panelHeader.addEventListener('click', () => {
        panelBody.style.display = panelBody.style.display === 'none' ? 'block' : 'none';
      });

      toolPanel.appendChild(panelHeader);
      toolPanel.appendChild(panelBody);
      bubble.appendChild(toolPanel);

      // Render Rich Interactive Result Cards
      const resultCardsContainer = renderResultCards(toolName, toolResult);
      if (resultCardsContainer) {
        bubble.appendChild(resultCardsContainer);
      }
    }

    chatThread.appendChild(bubble);
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  function removeBubble(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  // Render rich cards based on MCP tool results
  function renderResultCards(toolName, result) {
    if (!result) return null;

    const container = document.createElement('div');

    if (toolName === 'find_food') {
      const items = Array.isArray(result) ? result : (result.result || []);
      if (items.length > 0) {
        const grid = document.createElement('div');
        grid.style.display = 'grid';
        grid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(230px, 1fr))';
        grid.style.gap = '0.75rem';
        grid.style.marginTop = '0.75rem';

        items.forEach(item => {
          const card = document.createElement('div');
          card.className = 'card';
          card.style.padding = '0.9rem';
          card.style.backgroundColor = '#ffffff';

          const priceStr = item.price > 0 ? `₹${item.price.toFixed(0)}` : 'FREE';

          card.innerHTML = `
            <div style="font-weight:700; color:var(--navbar-green); font-size:1.05rem;">${escapeHtml(item.name)}</div>
            <div style="font-size:0.85rem; color:var(--text-muted);">🏢 ${escapeHtml(item.canteen)} &bull; 📍 ${item.distance_km} km</div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin:0.6rem 0;">
              <span class="badge badge-qty">${item.quantity} ${escapeHtml(item.unit)}s left</span>
              <strong style="color:var(--saffron); font-size:1.1rem;">${priceStr}</strong>
            </div>
            <button class="btn btn-saffron btn-sm" style="width:100%; margin-top:0.3rem;" onclick="reserveViaAssistant(${item.id}, '${escapeHtml(item.name)}')">
              ⚡ Order Now
            </button>
          `;
          grid.appendChild(card);
        });
        container.appendChild(grid);
        return container;
      }
    } else if (toolName === 'list_surplus_food') {
      const card = document.createElement('div');
      card.className = 'result-card success-card';
      const priceStr = (result.price && result.price > 0) ? `₹${result.price.toFixed(0)}` : 'Free';
      card.innerHTML = `
        <div style="display:flex; align-items:center; gap:0.5rem; font-weight:700; color:#1e8449;">
          <span>✅</span>
          <span>New Surplus Food Listed!</span>
        </div>
        <div style="margin-top:0.4rem; font-size:0.9rem;">
          <strong>${escapeHtml(result.name || '')}</strong> &mdash; ${result.quantity || 1} ${escapeHtml(result.unit || 'parcel')}s at ${priceStr}
        </div>
        <div style="font-size:0.8rem; color:var(--text-muted); margin-top:0.2rem;">
          Canteen: ${escapeHtml(result.canteen || 'My Canteen')} &bull; Safe until: ${escapeHtml(result.safe_until || '')} &bull; Distance: ${result.distance_km || 1} km
        </div>
      `;
      container.appendChild(card);
      return container;
    } else if (toolName === 'reserve_food' && result.success) {
      const card = document.createElement('div');
      card.className = 'result-card success-card';
      card.innerHTML = `
        <div style="display:flex; align-items:center; gap:0.5rem; font-weight:700; color:#1e8449;">
          <span>🎉</span>
          <span>Reservation Confirmed!</span>
        </div>
        <div style="margin:0.5rem 0; font-size:1.15rem; font-weight:800; color:var(--navbar-green);">
          Pickup Code: <span style="background:#d4efdf; padding:0.2rem 0.6rem; border-radius:6px; font-family:monospace;">${escapeHtml(result.pickup_code || '')}</span>
        </div>
        <div style="font-size:0.88rem; color:var(--text-dark);">
          Item: <strong>${escapeHtml(result.name || '')}</strong> at <strong>${escapeHtml(result.canteen || '')}</strong>
        </div>
        <div style="font-size:0.8rem; color:var(--text-muted); margin-top:0.2rem;">
          Show this code at counter for pickup. (${result.updated_quantity} portions remaining in stock)
        </div>
      `;
      container.appendChild(card);
      return container;
    } else if (toolName === 'remove_food' && result.success) {
      const card = document.createElement('div');
      card.className = 'result-card';
      card.style.background = '#fcf3cf';
      card.style.borderColor = '#f9e79f';
      card.innerHTML = `
        <div style="font-weight:700; color:#b7950b;">
          🗑️ Listing #${result.listing_id} Removed
        </div>
        <div style="font-size:0.85rem; color:var(--text-muted); margin-top:0.2rem;">
          This surplus food listing is now closed and no longer visible to customers.
        </div>
      `;
      container.appendChild(card);
      return container;
    }

    return null;
  }

  // Global helper for instant order button on cards
  window.reserveViaAssistant = (id, name) => {
    handleUserMessage(`reserve listing ${id}`);
  };

  // Text to speech
  function speakReply(text) {
    if (isMuted || !('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = langSelect.value || 'en-IN';
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn("Speech synthesis error:", e);
    }
  }

  function escapeHtml(str) {
    if (typeof str !== 'string') return String(str);
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
});
