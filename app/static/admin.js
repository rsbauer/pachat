const userList = document.getElementById('user-list');
const userDetail = document.getElementById('user-detail');
const userSearch = document.getElementById('user-search');
const pageStatus = document.getElementById('page-status');
const adminIdentity = document.getElementById('admin-identity');
const signOutButton = document.getElementById('admin-signout');

let users = [];
let selectedUserId = null;

function setStatus(message, isError = false) {
  pageStatus.textContent = message;
  pageStatus.classList.toggle('is-error', isError);
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function formatDate(value) {
  if (!value) return 'Unknown';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the HTTP status when the server does not return JSON.
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function updateMetrics() {
  const totals = users.reduce((result, user) => ({
    chats: result.chats + user.chat_count,
    files: result.files + user.file_count,
    storage: result.storage + user.storage_bytes,
  }), { chats: 0, files: 0, storage: 0 });
  document.getElementById('metric-users').textContent = users.length.toLocaleString();
  document.getElementById('metric-chats').textContent = totals.chats.toLocaleString();
  document.getElementById('metric-files').textContent = totals.files.toLocaleString();
  document.getElementById('metric-storage').textContent = formatBytes(totals.storage);
  document.getElementById('user-count').textContent = users.length.toLocaleString();
}

function renderUsers() {
  const filter = userSearch.value.trim().toLocaleLowerCase();
  const visibleUsers = users.filter((user) => `${user.username} ${user.display_name}`.toLocaleLowerCase().includes(filter));
  userList.replaceChildren();
  if (!visibleUsers.length) {
    userList.append(makeElement('p', 'list-empty', users.length ? 'No matching users.' : 'No user accounts found.'));
    return;
  }

  for (const user of visibleUsers) {
    const button = makeElement('button', `user-row${user.id === selectedUserId ? ' is-selected' : ''}`);
    button.type = 'button';
    button.setAttribute('aria-pressed', String(user.id === selectedUserId));
    const name = makeElement('span', 'user-row-name', user.display_name);
    const username = makeElement('span', 'user-row-meta', `@${user.username} | ${user.chat_count} chats | ${formatBytes(user.storage_bytes)}`);
    button.append(name, username);
    button.addEventListener('click', () => loadUser(user.id));
    userList.append(button);
  }
}

function renderSectionHeading(label, title, count) {
  const heading = makeElement('div', 'section-heading');
  const text = makeElement('div');
  text.append(makeElement('p', 'eyebrow', label), makeElement('h3', '', title));
  heading.append(text, makeElement('span', 'subtle-count', String(count)));
  return heading;
}

function renderUserDetail(detail) {
  const { user, sessions, documents, storage_bytes: storageBytes } = detail;
  userDetail.replaceChildren();

  const profile = makeElement('header', 'profile-heading');
  const profileText = makeElement('div');
  profileText.append(
    makeElement('p', 'eyebrow', `${user.role} account · joined ${formatDate(user.created_at)}`),
    makeElement('h2', '', user.display_name),
    makeElement('p', 'profile-username', `@${user.username}`),
  );
  const deleteUserButton = makeElement('button', 'danger-button', 'Delete user');
  deleteUserButton.type = 'button';
  deleteUserButton.addEventListener('click', () => removeUser(user));
  profile.append(profileText, deleteUserButton);

  const summary = makeElement('div', 'user-summary');
  summary.append(
    makeSummaryItem('Chats', sessions.length.toLocaleString()),
    makeSummaryItem('Files', documents.length.toLocaleString()),
    makeSummaryItem('File storage', formatBytes(storageBytes)),
  );

  const chatsSection = makeElement('section', 'detail-section');
  chatsSection.append(renderSectionHeading('History', 'Chats', sessions.length));
  const chatList = makeElement('div', 'chat-list');
  if (!sessions.length) chatList.append(makeElement('p', 'list-empty', 'No chats for this user.'));
  for (const session of sessions) {
    const row = makeElement('div', 'chat-row');
    const openButton = makeElement('button', 'chat-open');
    openButton.type = 'button';
    openButton.append(
      makeElement('span', 'chat-title', session.title),
      makeElement('span', 'chat-meta', `${session.message_count} messages · updated ${formatDate(session.updated_at)}`),
    );
    openButton.addEventListener('click', () => loadChat(session));
    const deleteButton = makeElement('button', 'icon-action danger-text', 'Delete');
    deleteButton.type = 'button';
    deleteButton.setAttribute('aria-label', `Delete chat: ${session.title}`);
    deleteButton.addEventListener('click', () => removeChat(session, user.id));
    row.append(openButton, deleteButton);
    chatList.append(row);
  }
  chatsSection.append(chatList);

  const filesSection = makeElement('section', 'detail-section');
  filesSection.append(renderSectionHeading('Stored documents', 'Files', documents.length));
  const fileList = makeElement('div', 'file-list');
  if (!documents.length) fileList.append(makeElement('p', 'list-empty', 'No files for this user.'));
  for (const file of documents) {
    const row = makeElement('div', 'file-row');
    const fileText = makeElement('div', 'file-description');
    fileText.append(
      makeElement('span', 'file-name', file.filename),
      makeElement('span', 'file-meta', `${formatBytes(file.size_bytes)} | ${file.mime_type} | ${file.is_encrypted ? 'Encrypted at rest' : 'Not encrypted'}`),
    );
    const deleteButton = makeElement('button', 'icon-action danger-text', 'Delete');
    deleteButton.type = 'button';
    deleteButton.setAttribute('aria-label', `Delete file: ${file.filename}`);
    deleteButton.addEventListener('click', () => removeFile(file, user.id));
    row.append(fileText, deleteButton);
    fileList.append(row);
  }
  filesSection.append(fileList);
  userDetail.append(profile, summary, chatsSection, filesSection);
}

function makeSummaryItem(label, value) {
  const item = makeElement('div', 'summary-item');
  item.append(makeElement('span', '', label), makeElement('strong', '', value));
  return item;
}

function showEmptyDetail(title, message) {
  const empty = makeElement('div', 'empty-detail');
  empty.append(makeElement('span', 'empty-rule'), makeElement('h2', '', title), makeElement('p', '', message));
  userDetail.replaceChildren(empty);
}

function renderChat(session) {
  const section = makeElement('section', 'detail-section transcript-section');
  const heading = makeElement('div', 'transcript-heading');
  const title = makeElement('div');
  title.append(
    makeElement('p', 'eyebrow', `Chat history | ${session.status}`),
    makeElement('h3', '', session.title),
  );
  const closeButton = makeElement('button', 'quiet-button', 'Close history');
  closeButton.type = 'button';
  closeButton.addEventListener('click', () => loadUser(selectedUserId));
  heading.append(title, closeButton);

  const messages = makeElement('div', 'transcript');
  for (const message of session.messages) {
    const item = makeElement('article', `transcript-message role-${message.role}`);
    item.append(
      makeElement('span', 'message-role', message.role),
      makeElement('p', 'message-content', message.content),
      makeElement('time', 'message-time', formatDate(message.created_at)),
    );
    messages.append(item);
  }
  section.append(heading, messages);
  userDetail.append(section);
}

async function loadUsers(selectId = selectedUserId) {
  users = await request('/api/admin/users');
  updateMetrics();
  renderUsers();
  if (selectId && users.some((user) => user.id === selectId)) await loadUser(selectId);
}

async function loadUser(userId) {
  selectedUserId = userId;
  renderUsers();
  try {
    const detail = await request(`/api/admin/users/${encodeURIComponent(userId)}`);
    renderUserDetail(detail);
    setStatus('Admin access active');
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadChat(session) {
  try {
    const detail = await request(`/api/admin/sessions/${encodeURIComponent(session.id)}`);
    renderChat(detail);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function removeUser(user) {
  if (!window.confirm(`Permanently delete ${user.username}, all their chats, and all their files?`)) return;
  try {
    await request(`/api/admin/users/${encodeURIComponent(user.id)}`, { method: 'DELETE' });
    selectedUserId = null;
    await loadUsers(null);
    showEmptyDetail('User deleted', 'The account, chat history, file records, and upload directory were removed.');
    setStatus(`Deleted ${user.username}`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function removeChat(session, userId) {
  if (!window.confirm(`Permanently delete the chat "${session.title}" and its messages?`)) return;
  try {
    await request(`/api/admin/sessions/${encodeURIComponent(session.id)}`, { method: 'DELETE' });
    await loadUsers(userId);
    setStatus('Chat deleted');
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function removeFile(file, userId) {
  if (!window.confirm(`Permanently delete ${file.filename}?`)) return;
  try {
    await request(`/api/admin/files/${encodeURIComponent(file.id)}`, { method: 'DELETE' });
    await loadUsers(userId);
    setStatus('File deleted');
  } catch (error) {
    setStatus(error.message, true);
  }
}

userSearch.addEventListener('input', renderUsers);
signOutButton.addEventListener('click', async () => {
  try {
    await request('/api/auth/logout', { method: 'POST' });
  } finally {
    window.location.assign('/');
  }
});

async function initialize() {
  try {
    const user = await request('/api/auth/me');
    if (user.role !== 'admin') {
      showEmptyDetail('Admin access required', 'Sign in with an account that has the admin role.');
      setStatus('Access denied', true);
      return;
    }
    adminIdentity.textContent = user.display_name;
    signOutButton.hidden = false;
    await loadUsers();
    setStatus('Admin access active');
  } catch (error) {
    showEmptyDetail('Sign in required', 'Sign in with an account that has the admin role to manage site data.');
    setStatus(error.message, true);
  }
}

initialize();