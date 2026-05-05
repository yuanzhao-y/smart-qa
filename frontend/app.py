"""Streamlit frontend for Smart QA."""

import requests
import streamlit as st

API_URL = "http://localhost:8000"

st.set_page_config(page_title="Smart QA", page_icon="📚", layout="wide")


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


@st.cache_data(ttl=10)
def fetch_stats():
    try:
        return requests.get(f"{API_URL}/stats", timeout=3).json()
    except Exception:
        return None


@st.cache_data(ttl=10)
def fetch_documents():
    try:
        resp = requests.get(f"{API_URL}/documents", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("documents", [])
    except Exception:
        pass
    return []


def stream_answer(question: str, history: list):
    try:
        resp = requests.post(
            f"{API_URL}/chat",
            json={"question": question, "history": history, "stream": True},
            stream=True,
            timeout=120,
        )
        if resp.status_code == 200:
            for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    yield chunk
        else:
            yield f"请求失败：{resp.text}"
    except requests.ConnectionError:
        yield "后端未连接，请先启动后端服务"


# --- Session state ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Sidebar ---
with st.sidebar:
    st.title("📚 Smart QA")
    st.caption("智能文档问答系统")
    st.divider()

    # Upload
    st.subheader("上传文档")
    uploaded_file = st.file_uploader(
        "选择文件",
        type=["pdf", "docx", "txt", "md"],
        help="支持 PDF、DOCX、TXT、Markdown",
    )
    if uploaded_file and st.button("上传并索引", use_container_width=True, type="primary"):
        with st.spinner("处理中..."):
            try:
                resp = requests.post(
                    f"{API_URL}/upload",
                    files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(f"成功！{data['pages']} 页，{data['chunks']} 片段")
                    fetch_stats.clear()
                    fetch_documents.clear()
                else:
                    st.error(f"失败：{resp.text}")
            except requests.ConnectionError:
                st.error("后端未连接")

    st.divider()

    # Stats
    stats = fetch_stats()
    if stats:
        st.metric("知识库片段数", stats.get("total_chunks", 0))
    else:
        st.warning("后端未连接")

    st.divider()

    # Document list
    st.subheader("已上传文档")
    docs = fetch_documents()
    if not docs:
        st.caption("暂无文档")
    for doc in docs:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text(f"📄 {doc['filename']}")
            st.caption(format_size(doc["size"]))
        with col2:
            if st.button("删除", key=f"del_{doc['file_id']}"):
                del_resp = requests.delete(f"{API_URL}/documents/{doc['file_id']}")
                if del_resp.status_code == 200:
                    fetch_stats.clear()
                    fetch_documents.clear()
                    st.rerun()
                else:
                    st.error("删除失败")

    st.divider()

    if st.button("清空聊天", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# --- Main area ---
st.header("Smart QA - 智能文档问答", divider="rainbow")

if not st.session_state.messages:
    st.info("👋 **欢迎使用 Smart QA**\n\n请先在左侧上传文档，然后在此处提问。\n\n支持 PDF、DOCX、TXT、Markdown 格式。")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            badges = " ".join(f"`📄 {s}`" for s in msg["sources"])
            st.markdown(f"**来源：** {badges}")

if question := st.chat_input("请输入你的问题..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[:-1]
        ]
        answer = st.write_stream(stream_answer(question, history))
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": [],
        })
