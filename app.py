import os
import base64
import tempfile
from langchain_community.document_loaders import (
    PyPDFLoader, Docx2txtLoader, CSVLoader, UnstructuredExcelLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_groq import GroqEmbeddings, ChatGroq
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
import streamlit as st
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load Groq API key from .env file
if "GROQ_API_KEY" not in os.environ:
    st.error("Groq API key not found in .env file. Please add it.")
    st.stop()

SUPPORTED_EXTENSIONS = {
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".csv": CSVLoader,
    ".xlsx": UnstructuredExcelLoader,
}

def display_pdf(uploaded_file):
    """Display an uploaded PDF file in the Streamlit sidebar."""
    base64_pdf = base64.b64encode(uploaded_file.read()).decode("utf-8")
    pdf_display = f"""
    <iframe
        src="data:application/pdf;base64,{base64_pdf}"
        width="100%"
        height="400px"
        type="application/pdf"
    ></iframe>
    """
    st.sidebar.markdown("### PDF Preview")
    st.sidebar.markdown(pdf_display, unsafe_allow_html=True)

def load_uploaded_files(uploaded_files):
    documents = []
    for uploaded_file in uploaded_files:
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        if file_extension in SUPPORTED_EXTENSIONS:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                    temp_file.write(uploaded_file.getvalue())
                    temp_file_path = temp_file.name
                
                loader = SUPPORTED_EXTENSIONS[file_extension](temp_file_path)
                if file_extension == ".pdf":
                    try:
                        documents.extend(loader.load())
                    except Exception as e:
                        st.warning(f"Error loading PDF file {uploaded_file.name}: {e}")
                else:
                    documents.extend(loader.load())
                
                os.unlink(temp_file_path)
            except Exception as e:
                st.warning(f"Error loading file {uploaded_file.name}: {e}")
        else:
            st.warning(f"Unsupported file type: {uploaded_file.name}. Skipping.")
    return documents

st.set_page_config(page_title="Document-Based Chatbot", page_icon="🤖", layout="wide")

with st.sidebar:
    st.title("Document Upload")
    uploaded_files = st.file_uploader(
        "Upload up to 5 documents (PDF, DOCX, CSV, XLSX)",
        type=["pdf", "docx", "csv", "xlsx"],
        accept_multiple_files=True,
    )

    if uploaded_files and len(uploaded_files) > 5:
        st.error("You can upload a maximum of 5 files at a time.")
        st.stop()

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "documents_processed" not in st.session_state:
        st.session_state.documents_processed = False
    
    if uploaded_files and not st.session_state.documents_processed:
        with st.spinner("Processing uploaded documents..."):
            documents = load_uploaded_files(uploaded_files)
            if documents:
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000,
                    chunk_overlap=200
                )
                texts = text_splitter.split_documents(documents)
                embeddings = GroqEmbeddings()
                vectorstore = FAISS.from_documents(texts, embeddings)
                st.session_state.vectorstore = vectorstore
                st.session_state.documents_processed = True
                st.success("Documents processed successfully! You can now ask questions.")
            else:
                st.error("No valid documents were processed. Please upload supported files.")
    
    # Display PDFs in sidebar
    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_extension = os.path.splitext(uploaded_file.name)[1].lower()
            if file_extension == ".pdf":
                display_pdf(uploaded_file)

st.title("Document-Based Chatbot 🤖")

# Display chat history
for message in st.session_state.chat_history:
    if message["role"] == "user":
        st.markdown(f'**You:** {message["content"]}')
    else:
        st.markdown(f'**ChatBot:** {message["content"]}')

# User input with send button
user_query = st.text_area("Ask a question about your documents:", key="user_input")
if st.button("Send"):
    if user_query and st.session_state.documents_processed:
        with st.spinner("Processing your query..."):
            llm = ChatGroq(temperature=0.1, model="llama-2-70b")
            memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
            qa_chain = ConversationalRetrievalChain.from_llm(
                llm=llm,
                retriever=st.session_state.vectorstore.as_retriever(),
                memory=memory,
            )
            try:
                result = qa_chain.invoke({"question": user_query})
                response = result['answer']
            except Exception as e:
                response = f"Error querying document QA: {e}"
            
            st.session_state.chat_history.append({"role": "user", "content": user_query})
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()
