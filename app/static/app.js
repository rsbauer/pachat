const messagesEl = document.getElementById('messages');
const chatForm = document.getElementById('chat-form');
const promptInput = document.getElementById('prompt');
const statusIndicator = document.getElementById('status-indicator');
const sendButton = document.getElementById('send-button');

const state = {
  messages: [],
};

function addMessage(role, text) {
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

function createRequestBody() {
  return {
    messages: state.messages.map((message) => ({ role: message.role, content: message.content })),
    stream: true,
    temperature: 0.7,
  };
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
      body: JSON.stringify(createRequestBody()),
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

        try {
          const parsed = JSON.parse(payload);
          if (parsed.error) {
            throw new Error(parsed.error);
          }
          const text = parsed.content || '';
          if (text) {
            bubble.textContent += text;
            messagesEl.scrollTop = messagesEl.scrollHeight;
          }
        } catch (error) {
          console.error('Invalid stream payload', error);
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
  }
}

chatForm.addEventListener('submit', sendPrompt);
