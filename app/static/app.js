const messagesEl = document.getElementById('messages');
const emptyState = document.getElementById('empty-state');
const chatDocumentStatus = document.getElementById('chat-document-status');
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
const authScreen = document.getElementById('auth-screen');
const appShell = document.getElementById('app-shell');
const authForm = document.getElementById('auth-form');
const authUsername = document.getElementById('auth-username');
const authPassword = document.getElementById('auth-password');
const authPasswordConfirm = document.getElementById('auth-password-confirm');
const confirmPasswordLabel = document.getElementById('confirm-password-label');
const authError = document.getElementById('auth-error');
const authSubmit = document.getElementById('auth-submit');
const authTitle = document.getElementById('auth-title');
const authDescription = document.getElementById('auth-description');
const showLoginButton = document.getElementById('show-login');
const showRegisterButton = document.getElementById('show-register');
const authTabs = document.querySelector('.auth-tabs');
const forgotPasswordButton = document.getElementById('forgot-password');
const recoveryForm = document.getElementById('recovery-form');
const recoveryUsername = document.getElementById('recovery-username');
const recoveryError = document.getElementById('recovery-error');
const recoverySubmit = document.getElementById('recovery-submit');
const passwordRequirement = document.getElementById('password-requirement');
const accountDisplayName = document.getElementById('account-display-name');
const profileDialog = document.getElementById('profile-dialog');
const filesDialog = document.getElementById('files-dialog');
const recoveryCodeDialog = document.getElementById('recovery-code-dialog');
const recoveryCodeValue = document.getElementById('recovery-code-value');
const managedFiles = document.getElementById('managed-files');

const state = {
  messages: [],
  sessionId: null,
  documentIds: [],
  availableDocuments: [],
  user: null,
  authMode: 'login',
};

async function apiFetch(url, options) {
  const response = await fetch(url, options);
  if (response.status === 401) {
    showAuthentication('login', 'Your session has ended. Sign in again to continue.');
    throw new Error('Please sign in again.');
  }
  return response;
}

function showAuthentication(mode, message = '') {
  state.user = null;
  document.querySelectorAll('dialog[open]').forEach((dialog) => dialog.close());
  appShell.hidden = true;
  authScreen.hidden = false;
  setAuthMode(mode);
  authError.textContent = message;
  authError.hidden = !message;
}

function setAuthMode(mode) {
  state.authMode = mode;
  const registering = mode === 'register';
  const recovering = mode === 'recover';
  authTitle.textContent = registering ? 'Create your account' : 'Welcome back';
  authDescription.textContent = registering
    ? 'Choose a username and a strong password.'
    : 'Sign in with your username and password.';
  if (recovering) {
    authTitle.textContent = 'Recover your account';
    authDescription.textContent = 'Enter your username and recovery code to set a new password.';
  }
  authSubmit.textContent = registering ? 'Create account' : 'Sign in';
  authPassword.autocomplete = registering ? 'new-password' : 'current-password';
  authPassword.minLength = registering ? 10 : 1;
  authPasswordConfirm.hidden = !registering;
  authPasswordConfirm.required = registering;
  confirmPasswordLabel.hidden = !registering;
  passwordRequirement.hidden = !registering;
  showLoginButton.classList.toggle('is-active', !registering);
  showLoginButton.setAttribute('aria-pressed', String(!registering));
  showRegisterButton.classList.toggle('is-active', registering);
  showRegisterButton.setAttribute('aria-pressed', String(registering));
  authTabs.hidden = recovering;
  authForm.hidden = recovering;
  recoveryForm.hidden = !recovering;
  forgotPasswordButton.hidden = registering || recovering;
  document.querySelector('.auth-footnote').hidden = recovering;
  recoveryError.hidden = true;
  authError.hidden = true;
}

async function responseJson(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || 'The request could not be completed.');
  return result;
}

async function enterApplication(user) {
  state.user = user;
  resetConversation(false);
  authScreen.hidden = true;
  appShell.hidden = false;
  accountDisplayName.textContent = user.display_name;
  await restoreSession();
}

function showRecoveryCode(code) {
  recoveryCodeValue.textContent = code;
  document.getElementById('recovery-copy-status').textContent = '';
  recoveryCodeDialog.showModal();
}

async function handleAuthentication(event) {
  event.preventDefault();
  authError.hidden = true;
  const isRegistering = state.authMode === 'register';
  if (isRegistering && authPassword.value !== authPasswordConfirm.value) {
    authError.textContent = 'Passwords do not match.';
    authError.hidden = false;
    return;
  }
  authSubmit.disabled = true;

  try {
    const response = await fetch(`/api/auth/${isRegistering ? 'register' : 'login'}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: authUsername.value.trim(), password: authPassword.value }),
    });
    const user = await responseJson(response);
    const recoveryCode = isRegistering ? user.recovery_code : null;
    delete user.recovery_code;
    authForm.reset();
    await enterApplication(user);
    if (recoveryCode) showRecoveryCode(recoveryCode);
  } catch (error) {
    authError.textContent = error.message;
    authError.hidden = false;
  } finally {
    authSubmit.disabled = false;
  }
}

async function handlePasswordRecovery(event) {
  event.preventDefault();
  recoveryError.hidden = true;
  const newPassword = document.getElementById('recovery-password').value;
  const confirmedPassword = document.getElementById('recovery-password-confirm').value;
  if (newPassword !== confirmedPassword) {
    recoveryError.textContent = 'New passwords do not match.';
    recoveryError.hidden = false;
    return;
  }

  recoverySubmit.disabled = true;
  try {
    const response = await fetch('/api/auth/recover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: recoveryUsername.value.trim(),
        recovery_code: document.getElementById('recovery-code').value.trim(),
        new_password: newPassword,
      }),
    });
    await responseJson(response);
    recoveryForm.reset();
    authForm.reset();
    setAuthMode('login');
    authError.textContent = 'Password updated. Sign in with your new password.';
    authError.hidden = false;
  } catch (error) {
    recoveryError.textContent = error.message;
    recoveryError.hidden = false;
  } finally {
    recoverySubmit.disabled = false;
  }
}

async function restoreAuthentication() {
  try {
    const response = await fetch('/api/auth/me');
    if (response.status === 401) {
      showAuthentication('login');
      return;
    }
    await enterApplication(await responseJson(response));
  } catch (error) {
    showAuthentication('login', 'Unable to connect. Please try again.');
  }
}

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

function resetConversation(removeStoredSession) {
  state.messages = [];
  state.sessionId = null;
  state.documentIds = [];
  if (removeStoredSession) localStorage.removeItem('pachat.sessionId');
  emptyState.hidden = false;
  messagesEl.replaceChildren(emptyState);
  updateChatDocumentStatus();
}

function updateChatDocumentStatus() {
  const selectedDocuments = state.availableDocuments.filter((file) => state.documentIds.includes(file.id));
  chatDocumentStatus.hidden = selectedDocuments.length === 0;
  chatDocumentStatus.textContent = selectedDocuments.length
    ? `Using ${selectedDocuments.length} file(s): ${selectedDocuments.map((file) => file.filename).join(', ')}`
    : '';
}

function createRequestBody(prompt) {
  return {
    message: prompt,
    session_id: state.sessionId,
    document_ids: state.documentIds,
    stream: true,
    temperature: 0.7,
  };
}

async function restoreSession() {
  const sessionId = localStorage.getItem('pachat.sessionId');
  if (!sessionId) return;

  try {
    const response = await apiFetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
    if (response.status === 404) {
      localStorage.removeItem('pachat.sessionId');
      return;
    }
    if (!response.ok) throw new Error('Could not restore chat history');

    const session = await response.json();
    state.sessionId = session.id;
    state.availableDocuments = session.documents || [];
    state.documentIds = state.availableDocuments.map((file) => file.id);
    updateChatDocumentStatus();
    state.messages = session.messages.map(({ role, content }) => ({ role, content }));
    state.messages.forEach(({ role, content }) => addMessage(role, content));
  } catch (error) {
    console.error(error);
    setStatus('History unavailable');
  }
}

function startNewChat() {
  resetConversation(true);
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
    const response = await apiFetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(createRequestBody(prompt)),
    });

    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.detail || 'Request failed');
    }
    if (!response.body) throw new Error('Request failed');

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
    bubble.textContent = error.message || 'The model request failed. Check the Ollama connection and worker logs.';
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
    const response = await apiFetch('/api/uploads', { method: 'POST', body: formData });
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

async function loadManagedFiles() {
  const filesStatus = document.getElementById('files-status');
  filesStatus.textContent = 'Loading files…';
  managedFiles.replaceChildren();
  try {
    const response = await apiFetch('/api/files');
    const files = await responseJson(response);
    state.availableDocuments = files;
    filesStatus.textContent = files.length ? '' : 'No files have been added yet.';
    updateChatDocumentStatus();
    for (const file of files) {
      const item = document.createElement('li');
      const details = document.createElement('div');
      details.className = 'file-details';
      const filename = document.createElement('strong');
      filename.textContent = file.filename;
      const metadata = document.createElement('span');
      metadata.textContent = `${formatFileSize(file.size_bytes)} · ${new Date(file.created_at).toLocaleDateString()}`;
      const useInChatLabel = document.createElement('label');
      useInChatLabel.className = 'file-chat-select';
      const useInChat = document.createElement('input');
      useInChat.type = 'checkbox';
      useInChat.checked = state.documentIds.includes(file.id);
      useInChat.setAttribute('aria-label', `Use ${file.filename} in this chat`);
      useInChat.addEventListener('change', () => {
        if (useInChat.checked && !state.documentIds.includes(file.id)) {
          if (state.documentIds.length >= 5) {
            useInChat.checked = false;
            filesStatus.textContent = 'Select no more than five files for a conversation.';
            return;
          }
          state.documentIds.push(file.id);
        } else {
          state.documentIds = state.documentIds.filter((documentId) => documentId !== file.id);
        }
        updateChatDocumentStatus();
      });
      useInChatLabel.append(useInChat, document.createTextNode('Use in this chat'));
      details.append(filename, metadata, useInChatLabel);

      const actions = document.createElement('div');
      actions.className = 'file-actions';
      const viewLink = document.createElement('a');
      viewLink.href = `/api/files/${encodeURIComponent(file.id)}`;
      viewLink.target = '_blank';
      viewLink.rel = 'noopener';
      viewLink.textContent = 'View';
      const deleteButton = document.createElement('button');
      deleteButton.type = 'button';
      deleteButton.textContent = 'Delete';
      deleteButton.addEventListener('click', () => deleteManagedFile(file));
      actions.append(viewLink, deleteButton);
      item.append(details, actions);
      managedFiles.appendChild(item);
    }
  } catch (error) {
    filesStatus.textContent = error.message;
  }
}

function formatFileSize(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

async function deleteManagedFile(file) {
  if (!window.confirm(`Delete ${file.filename}? This cannot be undone.`)) return;
  try {
    const response = await apiFetch(`/api/files/${encodeURIComponent(file.id)}`, { method: 'DELETE' });
    await responseJson(response);
    state.documentIds = state.documentIds.filter((documentId) => documentId !== file.id);
    updateChatDocumentStatus();
    await loadManagedFiles();
  } catch (error) {
    document.getElementById('files-status').textContent = error.message;
  }
}

async function saveProfile(event) {
  event.preventDefault();
  const status = document.getElementById('profile-status');
  const displayName = document.getElementById('profile-display-name').value.trim();
  if (!displayName) {
    status.textContent = 'Enter a display name.';
    return;
  }
  try {
    const response = await apiFetch('/api/auth/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName }),
    });
    state.user = await responseJson(response);
    accountDisplayName.textContent = state.user.display_name;
    status.textContent = 'Profile updated.';
  } catch (error) {
    status.textContent = error.message;
  }
}

async function savePassword(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.getElementById('password-status');
  const currentPassword = document.getElementById('current-password').value;
  const newPassword = document.getElementById('new-password').value;
  const confirmedPassword = document.getElementById('confirm-new-password').value;
  if (newPassword !== confirmedPassword) {
    status.textContent = 'New passwords do not match.';
    return;
  }
  try {
    const response = await apiFetch('/api/auth/password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    await responseJson(response);
    form.reset();
    status.textContent = 'Password updated.';
  } catch (error) {
    status.textContent = error.message;
  }
}

async function rotateRecoveryCode(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.getElementById('recovery-code-status');
  const currentPassword = document.getElementById('recovery-code-current-password').value;
  try {
    const response = await apiFetch('/api/auth/recovery-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currentPassword }),
    });
    const result = await responseJson(response);
    form.reset();
    status.textContent = '';
    showRecoveryCode(result.recovery_code);
  } catch (error) {
    status.textContent = error.message;
  }
}

async function copyRecoveryCode() {
  try {
    await navigator.clipboard.writeText(recoveryCodeValue.textContent);
    document.getElementById('recovery-copy-status').textContent = 'Code copied.';
  } catch (error) {
    document.getElementById('recovery-copy-status').textContent = 'Copy unavailable. Select the code to copy it.';
  }
}

async function signOut() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } finally {
    resetConversation(true);
    authForm.reset();
    showAuthentication('login', 'You have signed out.');
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
authForm.addEventListener('submit', handleAuthentication);
recoveryForm.addEventListener('submit', handlePasswordRecovery);
showLoginButton.addEventListener('click', () => setAuthMode('login'));
showRegisterButton.addEventListener('click', () => setAuthMode('register'));
forgotPasswordButton.addEventListener('click', () => setAuthMode('recover'));
document.getElementById('return-to-login').addEventListener('click', () => setAuthMode('login'));
document.getElementById('recovery-code-form').addEventListener('submit', rotateRecoveryCode);
document.getElementById('recovery-code-copy').addEventListener('click', copyRecoveryCode);
recoveryCodeDialog.addEventListener('close', () => {
  recoveryCodeValue.textContent = '';
});
document.getElementById('recovery-code-done').addEventListener('click', () => recoveryCodeDialog.close());
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
document.getElementById('profile-open').addEventListener('click', () => {
  document.getElementById('profile-username').value = state.user.username;
  document.getElementById('profile-display-name').value = state.user.display_name;
  document.getElementById('profile-status').textContent = '';
  document.getElementById('password-status').textContent = '';
  document.getElementById('recovery-code-status').textContent = '';
  profileDialog.showModal();
});
document.getElementById('files-open').addEventListener('click', () => {
  filesDialog.showModal();
  loadManagedFiles();
});
document.getElementById('logout').addEventListener('click', signOut);
document.getElementById('profile-form').addEventListener('submit', saveProfile);
document.getElementById('password-form').addEventListener('submit', savePassword);
document.querySelectorAll('[data-close-dialog]').forEach((button) => {
  button.addEventListener('click', () => document.getElementById(button.dataset.closeDialog).close());
});
restoreAuthentication();
