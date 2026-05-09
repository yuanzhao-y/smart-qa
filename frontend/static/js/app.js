const API = "http://localhost:8000";

// DOM refs
const $ = (s) => document.querySelector(s);
const welcomeScreen = $("#welcomeScreen");
const chatContainer = $("#chatContainer");
const messagesEl = $("#messages");
const chatInput = $("#chatInput");
const sendBtn = $("#sendBtn");
const stopBtn = $("#stopBtn");
const newChatBtn = $("#newChatBtn");
const clearChatBtn = $("#clearChatBtn");
const fileInput = $("#fileInput");
const uploadArea = $("#uploadArea");
const uploadStatus = $("#uploadStatus");
const uploadProgress = $("#uploadProgress");
const uploadProgressBar = $("#uploadProgressBar");
const docList = $("#docList");
const statsValue = $("#statsValue");
const sidebar = $("#sidebar");
const sidebarToggle = $("#sidebarToggle");
const historyList = $("#historyList");
const statsRow = $("#statsRow");
const chunksModal = $("#chunksModal");
const chunksModalClose = $("#chunksModalClose");
const chunksBody = $("#chunksBody");
const chunksFooter = $("#chunksFooter");
const summaryCard = $("#summaryCard");
const summaryDocType = $("#summaryDocType");
const summaryText = $("#summaryText");
const summaryKeywords = $("#summaryKeywords");
const summaryTopics = $("#summaryTopics");
const summaryClose = $("#summaryClose");
const attachBtn = $("#attachBtn");
const filePreview = $("#filePreview");
const dragOverlay = $("#dragOverlay");
let messages = [];
let isStreaming = false;
let currentSessionId = null;
let abortController = null;
let genIndex = 1;  // current generation index for this question
let pendingFiles = [];  // files selected but not yet uploaded

// Marked config with code block wrapper
const renderer = new marked.Renderer();
const originalCodeRenderer = renderer.code;
renderer.code = function(code, lang) {
    const highlighted = (lang && hljs.getLanguage(lang))
        ? hljs.highlight(code, { language: lang }).value
        : hljs.highlightAuto(code).value;
    return `<div class="code-block-wrapper"><button class="code-copy-btn" onclick="copyCode(this)" title="复制代码"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> 复制</button><pre><code class="hljs${lang ? ` language-${lang}` : ''}">${highlighted}</code></pre></div>`;
};

marked.setOptions({
    renderer: renderer,
    breaks: true,
    gfm: true,
});

function copyCode(btn) {
    const codeBlock = btn.parentElement.querySelector("code");
    const text = codeBlock.textContent;
    navigator.clipboard.writeText(text).then(() => {
        btn.classList.add("copied");
        btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> 已复制';
        setTimeout(() => {
            btn.classList.remove("copied");
            btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> 复制';
        }, 2000);
    });
}

function formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

// ===== Session Management =====
async function fetchSessions() {
    try {
        const resp = await fetch(`${API}/sessions`);
        const data = await resp.json();
        return data.sessions || [];
    } catch {
        return [];
    }
}

async function createSession(title = "新对话") {
    try {
        const resp = await fetch(`${API}/sessions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title }),
        });
        return await resp.json();
    } catch {
        return null;
    }
}

async function loadSession(sessionId) {
    try {
        const resp = await fetch(`${API}/sessions/${sessionId}`);
        return await resp.json();
    } catch {
        return null;
    }
}

async function saveSession(sessionId, msgs, title) {
    try {
        const body = { messages: msgs };
        if (title) body.title = title;
        await fetch(`${API}/sessions/${sessionId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
    } catch {}
}

async function deleteSession(sessionId) {
    try {
        await fetch(`${API}/sessions/${sessionId}`, { method: "DELETE" });
    } catch {}
}

function formatDate(ts) {
    const d = new Date(ts * 1000);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return "刚刚";
    if (diff < 3600000) return Math.floor(diff / 60000) + " 分钟前";
    if (diff < 86400000) return Math.floor(diff / 3600000) + " 小时前";
    if (diff < 172800000) return "昨天";
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

async function renderHistoryList() {
    const sessions = await fetchSessions();
    if (sessions.length === 0) {
        historyList.innerHTML = '<div class="history-empty">暂无历史对话</div>';
        return;
    }
    historyList.innerHTML = "";
    sessions.forEach((s) => {
        const item = document.createElement("div");
        item.className = "history-item" + (s.id === currentSessionId ? " active" : "");
        item.innerHTML = `
            <span class="history-icon">&#128172;</span>
            <div class="history-info">
                <div class="history-title">${s.title}</div>
                <div class="history-time">${formatDate(s.updated_at)}</div>
            </div>
            <button class="history-delete" title="删除">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
        `;
        item.addEventListener("click", (e) => {
            if (e.target.closest(".history-delete")) return;
            switchSession(s.id);
        });
        item.querySelector(".history-delete").addEventListener("click", async (e) => {
            e.stopPropagation();
            await deleteSession(s.id);
            if (s.id === currentSessionId) {
                currentSessionId = null;
                messages = [];
                showWelcome();
            }
            renderHistoryList();
        });
        historyList.appendChild(item);
    });
}

async function switchSession(sessionId) {
    if (isStreaming) return;
    const session = await loadSession(sessionId);
    if (!session) return;

    currentSessionId = sessionId;
    messages = session.messages || [];
    genIndex = 1;

    messagesEl.innerHTML = "";
    if (messages.length === 0) {
        showWelcome();
    } else {
        showChat();
        messages.forEach((m, i) => {
            const msgData = { msgIdx: i, evaluation: m.evaluation, feedback: m.feedback, timestamp: m.timestamp };
            renderMessage(m.role, m.content, msgData);
        });
    }
    renderHistoryList();
    chatInput.focus();
}

// ===== Chat =====
function showChat() {
    welcomeScreen.style.display = "none";
    chatContainer.style.display = "block";
}

function showWelcome() {
    welcomeScreen.style.display = "flex";
    chatContainer.style.display = "none";
}

function renderMessage(role, content, msgData) {
    const div = document.createElement("div");
    div.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "You" : "AI";

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    if (role === "user") {
        contentDiv.textContent = content;
    } else {
        contentDiv.innerHTML = parseCitations(marked.parse(content));
        if (msgData?.evaluation) {
            contentDiv.innerHTML += renderEvalBar(msgData.evaluation);
        }
        if (msgData?.msgIdx !== undefined) {
            contentDiv.innerHTML += renderFeedbackButtons(msgData.msgIdx, msgData?.feedback);
        }
    }

    // Timestamp
    const timeDiv = document.createElement("div");
    timeDiv.className = "message-time";
    timeDiv.textContent = msgData?.timestamp ? formatTime(msgData.timestamp) : formatTime(Date.now() / 1000);

    const wrapper = document.createElement("div");
    wrapper.style.display = "flex";
    wrapper.style.flexDirection = "column";
    wrapper.appendChild(contentDiv);
    wrapper.appendChild(timeDiv);

    div.appendChild(avatar);
    div.appendChild(wrapper);
    messagesEl.appendChild(div);
    scrollToBottom();
    return contentDiv;
}

let scrollRafId = null;
function scrollToBottom() {
    if (scrollRafId) return;
    scrollRafId = requestAnimationFrame(() => {
        chatContainer.scrollTop = chatContainer.scrollHeight;
        scrollRafId = null;
    });
}

// ===== Citation Parsing =====
function parseCitations(html) {
    return html.replace(
        /（来源[：:]([^，）,)]+)(?:[，,]第(\d+)(?:页|段|部分)?)?）/g,
        (match, source, page) => {
            const label = page ? `${source} #${page}` : source;
            return `<span class="citation-link" data-source="${escapeHtmlAttr(source)}" data-page="${page || ''}" title="点击查看来源片段">📄 ${escapeHtmlAttr(label)}</span>`;
        }
    );
}

function escapeHtmlAttr(text) {
    return text.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

document.addEventListener("click", (e) => {
    const link = e.target.closest(".citation-link");
    if (!link) return;
    const source = link.dataset.source;
    if (source) openChunksForSource(source);
});

async function openChunksForSource(source) {
    chunksModal.style.display = "flex";
    chunksBody.innerHTML = '<div class="chunks-loading">加载中...</div>';
    chunksFooter.innerHTML = "";
    try {
        const resp = await fetch(`${API}/chunks?source=${encodeURIComponent(source)}&page_size=50`);
        const data = await resp.json();
        renderChunks(data);
    } catch {
        chunksBody.innerHTML = '<div class="chunks-loading">加载失败</div>';
    }
}

// ===== Evaluation & Feedback =====
function renderEvalBar(evalResult) {
    if (!evalResult || evalResult.overall === 0) return "";
    const score = evalResult.overall;
    const cls = score >= 4 ? "high" : score >= 3 ? "mid" : "low";
    const dots = Array.from({ length: 5 }, (_, i) =>
        `<span class="eval-dot ${i < score ? "filled" : ""}"></span>`
    ).join("");
    return `
        <div class="eval-bar">
            <span class="eval-score ${cls}">${score}/5</span>
            <span class="eval-dots">${dots}</span>
            ${evalResult.reason ? `<span class="eval-reason">${evalResult.reason}</span>` : ""}
        </div>
    `;
}

function renderFeedbackButtons(messageIndex, existingFeedback) {
    const rating = existingFeedback?.rating || 0;
    const upClass = rating === 1 ? "active-up" : "";
    const downClass = rating === -1 ? "active-down" : "";
    return `
        <div class="feedback-row">
            <button class="feedback-btn ${upClass}" data-msg-idx="${messageIndex}" data-rating="1" title="有帮助">👍</button>
            <button class="feedback-btn ${downClass}" data-msg-idx="${messageIndex}" data-rating="-1" title="没帮助">👎</button>
        </div>
    `;
}

function renderActionButtons(messageIndex, question, existingFeedback, genIndex, genTotal) {
    const rating = existingFeedback?.rating || 0;
    const upClass = rating === 1 ? "active-up" : "";
    const downClass = rating === -1 ? "active-down" : "";
    const genLabel = genTotal > 1 ? `<span class="gen-label">${genIndex}/${genTotal}</span>` : "";
    return `
        <div class="action-row">
            <button class="action-btn regenerate-btn" data-msg-idx="${messageIndex}" data-question="${escapeHtmlAttr(question)}" title="重新生成">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                <span>重新生成</span>${genLabel}
            </button>
            <div class="feedback-group">
                <button class="feedback-btn ${upClass}" data-msg-idx="${messageIndex}" data-rating="1" title="有帮助">👍</button>
                <button class="feedback-btn ${downClass}" data-msg-idx="${messageIndex}" data-rating="-1" title="没帮助">👎</button>
            </div>
        </div>
    `;
}

function showStopBtn() {
    sendBtn.style.display = "none";
    stopBtn.style.display = "flex";
}

function hideStopBtn() {
    stopBtn.style.display = "none";
    sendBtn.style.display = "flex";
}

function stopGeneration() {
    if (abortController) abortController.abort();
}

function regenerateMessage(msgIdx, question) {
    if (isStreaming) return;
    genIndex++;
    // Remove old assistant message but keep user message
    if (messages.length > 0 && messages[messages.length - 1].role === "assistant") {
        messages.pop();
        const msgEls = messagesEl.querySelectorAll(".message");
        if (msgEls.length >= 1) {
            msgEls[msgEls.length - 1].remove();
        }
    }
    sendMessage(question, true);
}

document.addEventListener("click", async (e) => {
    const regenBtn = e.target.closest(".regenerate-btn");
    if (regenBtn) {
        const question = regenBtn.dataset.question;
        regenerateMessage(0, question);
        return;
    }

    const btn = e.target.closest(".feedback-btn");
    if (!btn) return;
    const msgIdx = parseInt(btn.dataset.msgIdx);
    const rating = parseInt(btn.dataset.rating);
    if (!currentSessionId || isNaN(msgIdx)) return;

    const currentRating = messages[msgIdx]?.feedback?.rating || 0;
    const newRating = currentRating === rating ? 0 : rating;

    if (!messages[msgIdx].feedback) messages[msgIdx].feedback = {};
    messages[msgIdx].feedback.rating = newRating;

    const row = btn.closest(".feedback-row");
    row.querySelectorAll(".feedback-btn").forEach((b) => {
        b.classList.remove("active-up", "active-down");
    });
    if (newRating === 1) row.querySelector('[data-rating="1"]').classList.add("active-up");
    if (newRating === -1) row.querySelector('[data-rating="-1"]').classList.add("active-down");

    try {
        await fetch(`${API}/feedback`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: currentSessionId,
                message_index: msgIdx,
                rating: newRating,
            }),
        });
    } catch {}
});

async function evaluateAnswer(question, answer, docs) {
    try {
        const resp = await fetch(`${API}/evaluate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, answer, docs }),
        });
        return await resp.json();
    } catch {
        return null;
    }
}

async function sendMessage(question, isRegenerate = false) {
    if (!question.trim() || isStreaming) return;

    // Upload pending files first
    if (pendingFiles.length > 0) {
        for (const file of pendingFiles) {
            const form = new FormData();
            form.append("file", file);
            try {
                const resp = await fetch(`${API}/upload`, { method: "POST", body: form });
                if (resp.ok) {
                    const data = await resp.json();
                    fetchStats();
                    fetchDocuments();
                    if (data.summary && data.summary.summary) {
                        showSummaryCard(data.summary);
                    }
                }
            } catch {}
        }
        pendingFiles = [];
        renderFilePreview();
    }

    if (!isRegenerate) genIndex = 1;
    isStreaming = true;
    sendBtn.disabled = true;
    showStopBtn();
    abortController = new AbortController();

    if (!currentSessionId) {
        const title = question.slice(0, 30) + (question.length > 30 ? "..." : "");
        const session = await createSession(title);
        if (session) currentSessionId = session.id;
    }

    if (messages.length === 0) showChat();

    const now = Date.now() / 1000;
    messages.push({ role: "user", content: question, timestamp: now });
    renderMessage("user", question, { timestamp: now });

    const aiDiv = renderMessage("assistant", "", { timestamp: now });
    aiDiv.classList.add("streaming-cursor");
    aiDiv.innerHTML = '<span class="typing-dots"><span>.</span><span>.</span><span>.</span></span>';

    const history = messages.slice(0, -1).map((m) => ({
        role: m.role,
        content: m.content,
    }));

    let fullText = "";
    let hasContent = false;
    let renderScheduled = false;
    let streamDone = false;

    function scheduleRender() {
        if (renderScheduled) return;
        renderScheduled = true;
        requestAnimationFrame(() => {
            renderScheduled = false;
            if (hasContent && !streamDone) {
                aiDiv.innerHTML = marked.parse(fullText);
                aiDiv.classList.add("streaming-cursor");
            }
            scrollToBottom();
        });
    }

    try {
        const resp = await fetch(`${API}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, history, stream: true }),
            signal: abortController.signal,
        });

        if (!resp.ok) {
            const err = await resp.text();
            throw new Error(err);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            fullText += chunk;

            if (!hasContent && fullText.trim()) {
                hasContent = true;
                aiDiv.innerHTML = "";
            }
            scheduleRender();
        }

        streamDone = true;
        aiDiv.classList.remove("streaming-cursor");
        aiDiv.innerHTML = parseCitations(marked.parse(fullText || "(空回复)"));
        messages.push({ role: "assistant", content: fullText, timestamp: Date.now() / 1000 });

        const msgIdx = messages.length - 1;
        aiDiv.innerHTML += renderActionButtons(msgIdx, question, null, genIndex, genIndex);

        evaluateAnswer(question, fullText, null).then((evalResult) => {
            if (evalResult && evalResult.overall > 0) {
                messages[msgIdx].evaluation = evalResult;
                const actionRow = aiDiv.querySelector(".action-row");
                if (actionRow) {
                    actionRow.insertAdjacentHTML("beforebegin", renderEvalBar(evalResult));
                }
                if (currentSessionId) saveSession(currentSessionId, messages);
            }
        });

        if (currentSessionId) {
            saveSession(currentSessionId, messages);
            renderHistoryList();
        }
    } catch (err) {
        streamDone = true;
        aiDiv.classList.remove("streaming-cursor");
        if (err.name === "AbortError") {
            if (fullText.trim()) {
                aiDiv.innerHTML = parseCitations(marked.parse(fullText)) + '<div style="color:#f59e0b;font-size:13px;margin-top:8px;">已停止生成</div>';
                messages.push({ role: "assistant", content: fullText, timestamp: Date.now() / 1000 });
                const msgIdx = messages.length - 1;
                aiDiv.innerHTML += renderActionButtons(msgIdx, question, null, genIndex, genIndex);
            } else {
                aiDiv.innerHTML = '<span style="color:#f59e0b">已停止生成</span>';
            }
        } else {
            aiDiv.innerHTML = `<span style="color:#ef4444">请求失败：${err.message}</span>`;
            messages.push({ role: "assistant", content: `请求失败：${err.message}`, timestamp: Date.now() / 1000 });
        }
        if (currentSessionId) {
            saveSession(currentSessionId, messages);
            renderHistoryList();
        }
    }

    abortController = null;
    isStreaming = false;
    hideStopBtn();
    sendBtn.disabled = !chatInput.value.trim();
    chatInput.focus();
}

// ===== Input =====
chatInput.addEventListener("input", () => {
    sendBtn.disabled = !chatInput.value.trim() || isStreaming;
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + "px";
});

chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!isStreaming && chatInput.value.trim()) {
            sendMessage(chatInput.value.trim());
            chatInput.value = "";
            chatInput.style.height = "auto";
            sendBtn.disabled = true;
        }
    }
});

sendBtn.addEventListener("click", () => {
    if (!isStreaming && chatInput.value.trim()) {
        sendMessage(chatInput.value.trim());
        chatInput.value = "";
        chatInput.style.height = "auto";
        sendBtn.disabled = true;
    }
});

stopBtn.addEventListener("click", stopGeneration);

// Quick actions
document.querySelectorAll(".quick-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        const q = btn.dataset.question;
        if (q) sendMessage(q);
    });
});

// ===== New Chat / Clear =====
function newChat() {
    currentSessionId = null;
    messages = [];
    genIndex = 1;
    messagesEl.innerHTML = "";
    showWelcome();
    renderHistoryList();
    chatInput.focus();
}

newChatBtn.addEventListener("click", newChat);
clearChatBtn.addEventListener("click", newChat);

// ===== Sidebar Toggle (mobile) =====
sidebarToggle.addEventListener("click", () => {
    sidebar.classList.toggle("open");
});

document.addEventListener("click", (e) => {
    if (window.innerWidth <= 768 && sidebar.classList.contains("open")) {
        if (!sidebar.contains(e.target) && e.target !== sidebarToggle) {
            sidebar.classList.remove("open");
        }
    }
});

// ===== Document Management =====
function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

async function fetchStats() {
    try {
        const resp = await fetch(`${API}/stats`);
        const data = await resp.json();
        statsValue.textContent = data.total_chunks ?? "--";
    } catch {
        statsValue.textContent = "--";
    }
}

async function fetchDocuments() {
    try {
        const resp = await fetch(`${API}/documents`);
        const data = await resp.json();
        const docs = data.documents || [];

        if (docs.length === 0) {
            docList.innerHTML = '<div class="doc-empty">暂无文档</div>';
            return;
        }

        docList.innerHTML = "";
        docs.forEach((doc) => {
            const ext = doc.filename.split(".").pop().toLowerCase();
            const icons = { pdf: "📕", docx: "📘", doc: "📘", txt: "📄", md: "📝" };
            const icon = icons[ext] || "📄";

            const item = document.createElement("div");
            item.className = "doc-item";

            const typeBadge = doc.doc_type ? `<span class="doc-type-badge">${doc.doc_type}</span>` : "";
            const summaryPreview = doc.summary ? `<div class="doc-summary-preview">${doc.summary}</div>` : "";

            item.innerHTML = `
                <span class="doc-icon">${icon}</span>
                <div class="doc-info">
                    <div class="doc-name" title="${doc.filename}">${doc.filename}</div>
                    <div class="doc-meta-line">
                        <span class="doc-size">${formatSize(doc.size)}</span>
                        ${typeBadge}
                    </div>
                    ${summaryPreview}
                </div>
                <button class="doc-delete" title="删除">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            `;

            item.querySelector(".doc-delete").addEventListener("click", async () => {
                try {
                    const r = await fetch(`${API}/documents/${doc.file_id}`, { method: "DELETE" });
                    if (r.ok) {
                        fetchStats();
                        fetchDocuments();
                    }
                } catch {}
            });

            docList.appendChild(item);
        });
    } catch {
        docList.innerHTML = '<div class="doc-empty">加载失败</div>';
    }
}

// Upload with progress animation
uploadArea.addEventListener("click", () => fileInput.click());

uploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadArea.classList.add("dragover");
});

uploadArea.addEventListener("dragleave", () => {
    uploadArea.classList.remove("dragover");
});

uploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadArea.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
        uploadFile(e.dataTransfer.files[0]);
    }
});

let attachMode = false;  // true when fileInput triggered by attach button

fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
        if (attachMode) {
            // Add to pending files
            for (const file of fileInput.files) {
                addPendingFile(file);
            }
        } else {
            // Sidebar upload - direct upload
            uploadFile(fileInput.files[0]);
        }
        fileInput.value = "";
        attachMode = false;
    }
});

// ===== Attach Button & File Preview =====
attachBtn.addEventListener("click", () => {
    attachMode = true;
    fileInput.click();
});

function addPendingFile(file) {
    pendingFiles.push(file);
    renderFilePreview();
}

function removePendingFile(index) {
    pendingFiles.splice(index, 1);
    renderFilePreview();
}

function renderFilePreview() {
    if (pendingFiles.length === 0) {
        filePreview.style.display = "none";
        filePreview.innerHTML = "";
        return;
    }
    filePreview.style.display = "flex";
    filePreview.innerHTML = "";
    pendingFiles.forEach((file, i) => {
        const ext = file.name.split(".").pop().toLowerCase();
        const icons = { pdf: "📕", docx: "📘", doc: "📘", txt: "📄", md: "📝" };
        const icon = icons[ext] || "📄";
        const chip = document.createElement("div");
        chip.className = "file-chip";
        chip.innerHTML = `
            <span class="file-chip-icon">${icon}</span>
            <span class="file-chip-name" title="${file.name}">${file.name}</span>
            <span class="file-chip-size">${formatSize(file.size)}</span>
            <button class="file-chip-remove" data-index="${i}" title="移除">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        `;
        chip.querySelector(".file-chip-remove").addEventListener("click", () => removePendingFile(i));
        filePreview.appendChild(chip);
    });
}

// Override uploadFile to also support pending files from attach button
const _originalUploadFile = uploadFile;

// ===== Full-screen Drag Overlay =====
let dragCounter = 0;

document.addEventListener("dragenter", (e) => {
    e.preventDefault();
    if (e.dataTransfer.types.includes("Files")) {
        dragCounter++;
        if (dragCounter === 1) dragOverlay.style.display = "flex";
    }
});

document.addEventListener("dragover", (e) => {
    e.preventDefault();
});

document.addEventListener("dragleave", (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter === 0) dragOverlay.style.display = "none";
});

document.addEventListener("drop", (e) => {
    e.preventDefault();
    dragCounter = 0;
    dragOverlay.style.display = "none";
    if (e.dataTransfer.files.length > 0) {
        // Add to pending files instead of uploading directly
        for (const file of e.dataTransfer.files) {
            addPendingFile(file);
        }
    }
});

async function uploadFile(file) {
    uploadStatus.style.display = "none";
    uploadProgress.style.display = "block";
    uploadProgressBar.style.width = "0%";

    // Animate progress bar
    let progress = 0;
    const progressInterval = setInterval(() => {
        progress = Math.min(progress + Math.random() * 15, 90);
        uploadProgressBar.style.width = progress + "%";
    }, 200);

    const form = new FormData();
    form.append("file", file);

    try {
        const resp = await fetch(`${API}/upload`, { method: "POST", body: form });
        clearInterval(progressInterval);
        uploadProgressBar.style.width = "100%";

        setTimeout(() => {
            uploadProgress.style.display = "none";
            uploadStatus.style.display = "block";
        }, 300);

        if (resp.ok) {
            const data = await resp.json();
            uploadStatus.className = "upload-status success";
            uploadStatus.textContent = `成功！${data.pages} 页，${data.chunks} 片段`;
            fetchStats();
            fetchDocuments();
            if (data.summary && data.summary.summary) {
                showSummaryCard(data.summary);
            }
        } else {
            const err = await resp.text();
            uploadStatus.className = "upload-status error";
            uploadStatus.textContent = `失败：${err}`;
        }
    } catch {
        clearInterval(progressInterval);
        uploadProgress.style.display = "none";
        uploadStatus.style.display = "block";
        uploadStatus.className = "upload-status error";
        uploadStatus.textContent = "后端未连接";
    }

    setTimeout(() => { uploadStatus.style.display = "none"; }, 4000);
}

// ===== Summary Card =====
function showSummaryCard(summary) {
    summaryDocType.textContent = summary.doc_type || "文档";
    summaryText.textContent = summary.summary || "";

    summaryKeywords.innerHTML = "";
    (summary.keywords || []).forEach((kw) => {
        const tag = document.createElement("span");
        tag.className = "summary-keyword";
        tag.textContent = kw;
        summaryKeywords.appendChild(tag);
    });

    summaryTopics.innerHTML = "";
    (summary.topics || []).forEach((t) => {
        const div = document.createElement("div");
        div.className = "summary-topic";
        div.textContent = t;
        summaryTopics.appendChild(div);
    });

    summaryCard.style.display = "block";
}

summaryClose.addEventListener("click", () => {
    summaryCard.style.display = "none";
});

// ===== Chunks Viewer =====
let chunksCurrentPage = 1;

statsRow.addEventListener("click", () => {
    chunksCurrentPage = 1;
    openChunksModal();
});

chunksModalClose.addEventListener("click", closeChunksModal);
chunksModal.addEventListener("click", (e) => {
    if (e.target === chunksModal) closeChunksModal();
});

function openChunksModal() {
    chunksModal.style.display = "flex";
    loadChunks(chunksCurrentPage);
}

function closeChunksModal() {
    chunksModal.style.display = "none";
}

async function loadChunks(page) {
    chunksBody.innerHTML = '<div class="chunks-loading">加载中...</div>';
    chunksFooter.innerHTML = "";
    try {
        const resp = await fetch(`${API}/chunks?page=${page}&page_size=15`);
        const data = await resp.json();
        renderChunks(data);
    } catch {
        chunksBody.innerHTML = '<div class="chunks-loading">加载失败</div>';
    }
}

function renderChunks(data) {
    const { chunks, total, page, pages } = data;
    if (chunks.length === 0) {
        chunksBody.innerHTML = '<div class="chunks-loading">知识库为空，请先上传文档</div>';
        return;
    }

    chunksBody.innerHTML = "";
    chunks.forEach((c, i) => {
        const card = document.createElement("div");
        card.className = "chunk-card";
        const globalIndex = (page - 1) * 15 + i + 1;
        card.innerHTML = `
            <div class="chunk-header">
                <div class="chunk-meta">
                    <span class="chunk-index">${globalIndex}</span>
                    <span class="chunk-source">${c.source}</span>
                    ${c.page !== "" ? `<span class="chunk-page">#${c.page}</span>` : ""}
                </div>
                <button class="chunk-toggle">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </button>
            </div>
            <div class="chunk-content">${escapeHtml(c.content)}</div>
        `;
        const header = card.querySelector(".chunk-header");
        const content = card.querySelector(".chunk-content");
        const toggle = card.querySelector(".chunk-toggle");
        header.addEventListener("click", () => {
            content.classList.toggle("open");
            toggle.classList.toggle("open");
        });
        chunksBody.appendChild(card);
    });

    if (pages > 1) {
        let html = `<button class="page-btn" ${page <= 1 ? "disabled" : ""} onclick="loadChunks(${page - 1})">上一页</button>`;
        html += `<span class="page-info">${page} / ${pages}</span>`;
        html += `<button class="page-btn" ${page >= pages ? "disabled" : ""} onclick="loadChunks(${page + 1})">下一页</button>`;
        chunksFooter.innerHTML = html;
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ===== Init =====
fetchStats();
fetchDocuments();
renderHistoryList();
chatInput.focus();

// Typing dots animation
const style = document.createElement("style");
style.textContent = `
.typing-dots span { animation: dotBlink 1.4s infinite; font-size: 24px; font-weight: bold; color: var(--text-secondary); }
.typing-dots span:nth-child(2) { animation-delay: .2s; }
.typing-dots span:nth-child(3) { animation-delay: .4s; }
@keyframes dotBlink { 0%, 20% { opacity: .2; } 50% { opacity: 1; } 80%, 100% { opacity: .2; } }
`;
document.head.appendChild(style);
