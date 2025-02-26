import streamlit as st
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import uuid

# Load environment variables from .env file
load_dotenv()

USERNAME = os.getenv("CHATBOT_USERNAME")
PASSWORD = os.getenv("CHATBOT_PASSWORD")
API_URL = os.getenv("API_URL")

def load_custom_css():
    """Load custom CSS styles from external file"""
    with open('.streamlit/styles.css') as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session states
if 'chat_visible' not in st.session_state:
    st.session_state.chat_visible = False
if 'is_authenticated' not in st.session_state:
    st.session_state.is_authenticated = False
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'session_id' not in st.session_state:
    st.session_state.session_id = None
if 'feedback_states' not in st.session_state:
    st.session_state.feedback_states = {}
if 'show_feedback_categories' not in st.session_state:
    st.session_state.show_feedback_categories = {}

def handle_feedback(message_idx, feedback_type):
    """Handle thumbs up/down feedback"""
    if feedback_type == "down":
        st.session_state.show_feedback_categories[message_idx] = True
    else:
        # Store positive feedback
        st.session_state.feedback_states[message_idx] = {
            "feedback_id": str(uuid.uuid4()),
            "message_id": message_idx,
            "session_id": st.session_state.session_id,
            "feedback_type": "positive",
            "timestamp": datetime.now().isoformat(),
            "message_content": st.session_state.messages[message_idx]["content"]
        }
        # You can add API call here to store positive feedback

def submit_negative_feedback(message_idx, categories, correction_text):
    """Submit negative feedback with categories and correction"""
    st.session_state.feedback_states[message_idx] = {
        "feedback_id": str(uuid.uuid4()),
        "message_id": message_idx,
        "session_id": st.session_state.session_id,
        "feedback_type": "negative",
        "categories": categories,
        "correction": correction_text,
        "timestamp": datetime.now().isoformat(),
        "message_content": st.session_state.messages[message_idx]["content"]
    }
    # Hide the feedback categories after submission
    st.session_state.show_feedback_categories[message_idx] = False
    # You can add API call here to store negative feedback

def display_reference_details(ref):
    """Display details for a single reference"""
    if uri := ref.get('uri'):
        st.markdown(
            f'''
            <div class="reference-section">
                <div class="reference-section-title">Source:</div>
                <div class="reference-uri">{uri}</div>
            </div>
            ''', 
            unsafe_allow_html=True
        )
    
    if snippet := ref.get('snippet'):
        st.markdown(
            f'''
            <div class="reference-section">
                <div class="reference-section-title">Excerpt:</div>
                <div class="reference-snippet">{snippet}</div>
            </div>
            ''', 
            unsafe_allow_html=True
        )
    
    if presigned_url := ref.get('presigned_url'):
        st.markdown(
            f'''
            <div class="reference-footer">
                <a href="{presigned_url}" target="_blank">View Source Document</a>
                <p>Note: Source document link expires in 1 hour</p>
            </div>
            ''', 
            unsafe_allow_html=True
        )

def show_references(references, message_idx):
    """Display references in a compact horizontal list format"""
    if not references:
        return

    ref_key = f"selected_ref_{message_idx}"
    button_key = f"ref_button_clicked_{message_idx}"
    
    if ref_key not in st.session_state:
        st.session_state[ref_key] = 0
    if button_key not in st.session_state:
        st.session_state[button_key] = False

    with st.expander("📚 References", expanded=False):
        cols = st.columns(len(references))
        
        for i, col in enumerate(cols):
            with col:
                if st.button(
                    f"Reference {i+1}",
                    key=f"ref_btn_{message_idx}_{i}",
                    use_container_width=True
                ):
                    st.session_state[ref_key] = i
                    st.session_state[button_key] = True
        
        if 0 <= st.session_state[ref_key] < len(references):
            selected_ref = references[st.session_state[ref_key]]
            display_reference_details(selected_ref)

def call_api(query, session_id=None):
    """Call the Lambda function through API Gateway"""
    try:
        request_body = {
            "user_query": query
        }
        if session_id:
            request_body["sessionId"] = session_id
            
        print(f"Request Body, url: {request_body}, API_URL: {API_URL}")
        response = requests.post(
            url=API_URL,
            headers={"Content-Type": "application/json"},
            json=request_body,
            timeout=30
        )
        # print(f"Response: {response.json()}")
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"API Error: {str(e)}")
        return None

def authenticate(username, password):
    
    if username == USERNAME and password == PASSWORD:
        st.session_state.is_authenticated = True
        return True
    return False

def clear_chat():
    st.session_state.messages = []
    st.session_state.session_id = None

def logout():
    st.session_state.is_authenticated = False
    st.session_state.messages = []
    st.session_state.chat_visible = False
    st.session_state.session_id = None


def display_chat_messages():
    # Create a container for the entire chat area
    with st.container():
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        
        # Messages container
        with st.container():
            st.markdown('<div class="chat-messages">', unsafe_allow_html=True)
            for idx, message in enumerate(st.session_state.messages):
                message_class = "user-message" if message["role"] == "user" else "assistant-message"
                st.markdown(f'<div class="{message_class}">{message["content"]}</div>', unsafe_allow_html=True)
                
        # Show feedback buttons only for assistant messages
        if message["role"] == "assistant":
            col1, col2, col3 = st.columns([0.1, 0.1, 0.8])
            
            # Don't show feedback buttons if feedback already provided
            if idx not in st.session_state.feedback_states:
                with col1:
                    if st.button("👍", key=f"thumbsup_{idx}"):
                        handle_feedback(idx, "up")
                        st.rerun()
                with col2:
                    if st.button("👎", key=f"thumbsdown_{idx}"):
                        handle_feedback(idx, "down")
                        st.rerun()
            
            # Show feedback categories if thumbs down was clicked
            if idx in st.session_state.show_feedback_categories and st.session_state.show_feedback_categories[idx]:
                with st.container():
                    st.write("Please help us improve by selecting the issues:")
                    feedback_categories = {
                        "Incorrect Information": st.checkbox("Incorrect Information", key=f"cat1_{idx}"),
                        "Incomplete Answer": st.checkbox("Incomplete Answer", key=f"cat2_{idx}"),
                        "Not Relevant": st.checkbox("Not Relevant", key=f"cat3_{idx}"),
                        "Unclear Response": st.checkbox("Unclear Response", key=f"cat4_{idx}"),
                        "Other": st.checkbox("Other", key=f"cat5_{idx}")
                    }
                    
                    correction = st.text_area(
                        "Please provide the correct information or additional details (optional):",
                        key=f"correction_{idx}"
                    )
                    
                    if st.button("Submit Feedback", key=f"submit_feedback_{idx}"):
                        selected_categories = [
                            cat for cat, selected in feedback_categories.items() 
                            if selected
                        ]
                        submit_negative_feedback(idx, selected_categories, correction)
                        st.rerun()

                    
                if "references" in message:
                    show_references(message["references"], idx)
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Chat input will automatically be placed at the bottom
        st.markdown('</div>', unsafe_allow_html=True)


def display_chat_messages():
    for idx, message in enumerate(st.session_state.messages):
        message_class = "user-message" if message["role"] == "user" else "assistant-message"
        st.markdown(f'<div class="{message_class}">{message["content"]}</div>', unsafe_allow_html=True)
        
        # Show feedback buttons only for assistant messages
        if message["role"] == "assistant":
            col1, col2, col3 = st.columns([0.1, 0.1, 0.8])
            
            # Don't show feedback buttons if feedback already provided
            if idx not in st.session_state.feedback_states:
                with col1:
                    if st.button("👍", key=f"thumbsup_{idx}"):
                        handle_feedback(idx, "up")
                        st.rerun()
                with col2:
                    if st.button("👎", key=f"thumbsdown_{idx}"):
                        handle_feedback(idx, "down")
                        st.rerun()
            
            # Show feedback categories if thumbs down was clicked
            if idx in st.session_state.show_feedback_categories and st.session_state.show_feedback_categories[idx]:
                with st.container():
                    st.write("Please help us improve by selecting the issues:")
                    feedback_categories = {
                        "Incorrect Information": st.checkbox("Incorrect Information", key=f"cat1_{idx}"),
                        "Incomplete Answer": st.checkbox("Incomplete Answer", key=f"cat2_{idx}"),
                        "Not Relevant": st.checkbox("Not Relevant", key=f"cat3_{idx}"),
                        "Unclear Response": st.checkbox("Unclear Response", key=f"cat4_{idx}"),
                        "Other": st.checkbox("Other", key=f"cat5_{idx}")
                    }
                    
                    correction = st.text_area(
                        "Please provide the correct information or additional details (optional):",
                        key=f"correction_{idx}"
                    )
                    
                    if st.button("Submit Feedback", key=f"submit_feedback_{idx}"):
                        selected_categories = [
                            cat for cat, selected in feedback_categories.items() 
                            if selected
                        ]
                        submit_negative_feedback(idx, selected_categories, correction)
                        st.rerun()

            if "references" in message:
                show_references(message["references"], idx)

# [Previous functions remain the same: call_api, authenticate, clear_chat, logout, handle_chat_input]
def handle_chat_input(user_input):
    if user_input:
        # Add user message
        st.session_state.messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().strftime("%H:%M")
        })
        
        # Process the message and generate response
        with st.spinner("Processing your request..."):
            api_response = call_api(user_input, st.session_state.session_id)
            
            if api_response:
                if isinstance(api_response, str):
                    api_response = json.loads(api_response)
                if 'body' in api_response:
                    api_response = json.loads(api_response['body'])
                
                response_content = api_response.get('generated_response', 'No response available')
                detailed_references = api_response.get('detailed_references', [])
                
                if 'sessionId' in api_response:
                    st.session_state.session_id = api_response['sessionId']
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_content,
                    "references": detailed_references,
                    "timestamp": datetime.now().strftime("%H:%M")
                })
            else:
                st.error("Failed to get response from API")

def create_layout():
    with st.container():
        header_col, _, chat_button_col = st.columns([0.7, 0.2, 0.1])
        
        with header_col:
            st.title("Main Content")
        
        with chat_button_col:
            if not st.session_state.chat_visible:
                if st.button("💬 Chat"):
                    st.session_state.chat_visible = True
                    st.rerun()

    if st.session_state.chat_visible:
        main_content, chat_panel = st.columns([0.6, 0.4])
        
        with main_content:
            st.write("This is the main content area")
            st.image("assets/background.png", use_container_width=True)
            
        with chat_panel:
            col1, col2, col3 = st.columns([8, 1, 1])

            with col1:
                st.image("assets/header.png", use_container_width=True)
                
            with col2:
                if st.button("🔄", key="refresh_chat", help="Refresh"):
                    clear_chat()
                    st.rerun()
                    
            with col3:
                if st.button("X", key="logout_chat", help="Logout"):
                    logout()
                    st.rerun()

            if not st.session_state.is_authenticated:
                with st.form("login_form"):
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    submit_button = st.form_submit_button("Login")
                    
                    if submit_button:
                        if authenticate(username, password):
                            st.success("Successfully logged in!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password")
            else:
                display_chat_messages()
                st.markdown('<div class="chat-input-container">', unsafe_allow_html=True)
                st.markdown('<div class="chat-input-container">', unsafe_allow_html=True)

                user_input = st.chat_input("Just Ask...", key="chat_input")
                if user_input:
                    handle_chat_input(user_input)
                    st.rerun()
    else:
        st.write("This is the main content area")
        st.image("assets/background.png", use_container_width=True)

def main():
    st.set_page_config(
        page_title="Chat Application",
        page_icon="💬",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    load_custom_css()
    create_layout()

if __name__ == "__main__":
    main()