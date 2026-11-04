const messagesEl = document.getElementById('messages');
const emptyState = document.getElementById('empty-state');
const chatForm = document.getElementById('chat-form');
const promptInput = document.getElementById('prompt');
const statusIndicator = document.getElementById('status-indicator');
const sendButton = document.getElementById('send-button');
const newChatButton = document.getElementById('new-chat');
const uploadForm = document.getElementById('upload-form');
const documentFiles = document.getElementById('document-files');
const uploadStatus = document.getElementById('upload-status');
const uploadResults = document.getElementById('upload-results');
const uploadButton = document.getElementById('upload-button');
const dropArea = document.getElementById('drop-area');

const state = {
  messages: [],
  sessionId: null,
};

function addMessage(role, text) {
  emptyState.hidden = true;
  const row = document.createElement('div');
  row.className = `message ${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;

  row.appendChild(bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setStatus(text) {
  statusIndicator.textContent = text;
}

function createRequestBody(prompt) {
  return {
    message: prompt,
    session_id: state.sessionId,
    stream: true,
    temperature: 0.7,
  };
}

async function restoreSession() {
  const sessionId = localStorage.getItem('pachat.sessionId');
  if (!sessionId) return;

  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
    if (response.status === 404) {
      localStorage.removeItem('pachat.sessionId');
      return;
    }
    if (!response.ok) throw new Error('Could not restore chat history');

    const session = await response.json();
    state.sessionId = session.id;
    state.messages = session.messages.map(({ role, content }) => ({ role, content }));
    state.messages.forEach(({ role, content }) => addMessage(role, content));
  } catch (error) {
    console.error(error);
    setStatus('History unavailable');
  }
}

function startNewChat() {
  state.messages = [];
  state.sessionId = null;
  localStorage.removeItem('pachat.sessionId');
  emptyState.hidden = false;
  messagesEl.replaceChildren(emptyState);
  setStatus('Ready');
  promptInput.focus();
}

async function sendPrompt(event) {
  event.preventDefault();

  const prompt = promptInput.value.trim();
  if (!prompt) return;

  state.messages.push({ role: 'user', content: prompt });
  addMessage('user', prompt);
  promptInput.value = '';
  promptInput.focus();
  setStatus('Generating…');
  sendButton.disabled = true;
  newChatButton.disabled = true;

  const assistantBubble = document.createElement('div');
  assistantBubble.className = 'message assistant';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = '';
  assistantBubble.appendChild(bubble);
  messagesEl.appendChild(assistantBubble);

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(createRequestBody(prompt)),
    });

    if (!response.ok || !response.body) {
      throw new Error('Request failed');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() || '';

      for (const chunk of chunks) {
        const data = chunk.trim();
        if (!data.startsWith('data:')) continue;

        const payload = data.replace(/^data:\s*/, '');
        if (payload === '[DONE]') {
          continue;
        }

        let parsed;
        try {
          parsed = JSON.parse(payload);
        } catch (error) {
          console.error('Invalid stream payload', error);
          continue;
        }

        if (parsed.session_id) {
          state.sessionId = parsed.session_id;
          localStorage.setItem('pachat.sessionId', state.sessionId);
        }
        if (parsed.error) throw new Error(parsed.error);

        const text = parsed.content || '';
        if (text) {
          bubble.textContent += text;
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
      }
    }

    state.messages.push({ role: 'assistant', content: bubble.textContent });
    setStatus('Ready');
  } catch (error) {
    bubble.textContent = 'The model request failed. Check the Ollama connection and worker logs.';
    console.error(error);
    setStatus('Error');
  } finally {
    sendButton.disabled = false;
    newChatButton.disabled = false;
  }
}

async function uploadDocuments(files) {
  if (!files.length) {
    uploadStatus.textContent = 'Select or drop one or more files first.';
    return;
  }

  const formData = new FormData();
  for (const file of files) formData.append('files', file);
  uploadButton.disabled = true;
  uploadStatus.textContent = `Scanning and saving ${files.length} file(s)…`;
  uploadResults.textContent = '';

  try {
    const response = await fetch('/api/uploads', { method: 'POST', body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Upload failed');

    for (const file of result.uploaded) {
      const item = document.createElement('li');
      item.textContent = `Saved: ${file.filename}`;
      uploadResults.appendChild(item);
    }
    for (const file of result.rejected) {
      const item = document.createElement('li');
      item.textContent = `Not saved: ${file.filename} (${file.reason})`;
      uploadResults.appendChild(item);
    }
    uploadStatus.textContent = `${result.uploaded.length} file(s) saved.`;
    documentFiles.value = '';
  } catch (error) {
    uploadStatus.textContent = error.message;
  } finally {
    uploadButton.disabled = false;
  }
}

function handleDragOver(event) {
  event.preventDefault();
  dropArea.classList.add('is-dragging');
}

function handleDragLeave(event) {
  event.preventDefault();
  if (!dropArea.contains(event.relatedTarget)) {
    dropArea.classList.remove('is-dragging');
  }
}

chatForm.addEventListener('submit', sendPrompt);
uploadForm.addEventListener('submit', (event) => {
  event.preventDefault();
  uploadDocuments(documentFiles.files);
});
dropArea.addEventListener('dragenter', handleDragOver);
dropArea.addEventListener('dragover', handleDragOver);
dropArea.addEventListener('dragleave', handleDragLeave);
dropArea.addEventListener('drop', (event) => {
  event.preventDefault();
  dropArea.classList.remove('is-dragging');
  if (!event.dataTransfer.files.length) {
    uploadStatus.textContent = 'No files detected. Try again or use the file picker.';
    return;
  }
  uploadDocuments(event.dataTransfer.files);
});
newChatButton.addEventListener('click', startNewChat);
restoreSession();
