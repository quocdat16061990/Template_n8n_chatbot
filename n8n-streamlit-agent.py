import streamlit as st
import requests
import uuid
from supabase import create_client, Client
import pickle
import os
from datetime import datetime, timedelta

# Hàm đọc nội dung từ file văn bản
def rfile(name_file):
    try:
        with open(name_file, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        st.error(f"File {name_file} không tồn tại.")

# Constants
WEBHOOK_URL = rfile("WEBHOOK_URL.txt").strip()
SUPABASE_URL = rfile("SUPABASE_URL.txt").strip()
SUPABASE_KEY = rfile("SUPABASE_KEY.txt").strip()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# File để lưu auth state
AUTH_STATE_FILE = "auth_state.pkl"

# Hàm lưu auth state vào file
def save_auth_state(auth_data):
    try:
        auth_info = {
            'user_id': auth_data.user.id if auth_data.user else None,
            'email': auth_data.user.email if auth_data.user else None,
            'access_token': auth_data.session.access_token if auth_data.session else None,
            'refresh_token': auth_data.session.refresh_token if auth_data.session else None,
            'expires_at': auth_data.session.expires_at if auth_data.session else None,
            'saved_at': datetime.now().timestamp()
        }
        with open(AUTH_STATE_FILE, 'wb') as f:
            pickle.dump(auth_info, f)
    except Exception as e:
        st.error(f"Lỗi khi lưu trạng thái đăng nhập: {str(e)}")

# Hàm đọc auth state từ file
def load_auth_state():
    try:
        if os.path.exists(AUTH_STATE_FILE):
            with open(AUTH_STATE_FILE, 'rb') as f:
                auth_info = pickle.load(f)
                
            # Kiểm tra xem token có còn hợp lệ không
            if auth_info.get('expires_at'):
                expires_at = datetime.fromtimestamp(auth_info['expires_at'])
                if datetime.now() < expires_at:
                    return auth_info
                else:
                    # Token hết hạn, thử refresh
                    return refresh_auth_token(auth_info)
            return auth_info
    except Exception as e:
        st.error(f"Lỗi khi đọc trạng thái đăng nhập: {str(e)}")
    return None

# Hàm refresh token
def refresh_auth_token(auth_info):
    try:
        if auth_info.get('refresh_token'):
            res = supabase.auth.refresh_session(auth_info['refresh_token'])
            if res and res.session:
                # Cập nhật auth info mới
                updated_auth_info = {
                    'user_id': res.user.id if res.user else auth_info.get('user_id'),
                    'email': res.user.email if res.user else auth_info.get('email'),
                    'access_token': res.session.access_token,
                    'refresh_token': res.session.refresh_token,
                    'expires_at': res.session.expires_at,
                    'saved_at': datetime.now().timestamp()
                }
                # Lưu lại
                with open(AUTH_STATE_FILE, 'wb') as f:
                    pickle.dump(updated_auth_info, f)
                return updated_auth_info
    except Exception as e:
        st.error(f"Lỗi khi refresh token: {str(e)}")
    return None

# Hàm xóa auth state
def clear_auth_state():
    try:
        if os.path.exists(AUTH_STATE_FILE):
            os.remove(AUTH_STATE_FILE)
    except Exception as e:
        st.error(f"Lỗi khi xóa trạng thái đăng nhập: {str(e)}")

# Hàm lưu vào session_state thay vì localStorage
def session_storage_set(key, value):
    st.session_state[key] = value
    print(f"Session state set: {key} = {value}")  # In ra thông tin đã lưu

# Hàm lấy dữ liệu từ session_state
def generate_session_id():
    # Nếu chưa có session_id trong session_state, tạo mới và lưu lại
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    return st.session_state.session_id


def generate_session_id():
    return str(uuid.uuid4())

def login(email: str, password: str):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if res and res.user:
            # Lưu auth state vào session_state và file
            save_auth_state(res)
            st.session_state.auth = res  # Lưu vào session_state
        return res
    except Exception as e:
        st.error(f"Đăng nhập thất bại: {str(e)}")
        return None

def signup(email: str, password: str):
    try:
        res = supabase.auth.sign_up({"email": email, "password": password})
        return res
    except Exception as e:
        st.error(f"Đăng ký thất bại: {str(e)}")
        return None

def send_message_to_llm(session_id, message, access_token):
    session_id = st.session_state.get("session_id")
    if not session_id:
        session_id = generate_session_id()  # Nếu session_id không tồn tại, tạo mới và lưu lại
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "sessionId": session_id,
        "chatInput": message
    }
    try:
        response = requests.post(WEBHOOK_URL, json=payload, headers=headers)
        response.raise_for_status()
        response_data = response.json()
        print("Response status code:", response)  
        print("Full response:", response_data)  
        return response_data.get("output", "No output received")  # Trả về "output"
    except requests.exceptions.RequestException as e:
        return f"Error: Failed to connect to the LLM - {str(e)}"

def init_session_state():
    if "auth" not in st.session_state:
        # Thử load auth state từ file
        saved_auth = load_auth_state()
        if saved_auth:
            # Tạo mock auth object từ saved data
            class MockAuth:
                def __init__(self, auth_info):
                    self.user = type('User', (), {
                        'id': auth_info.get('user_id'),
                        'email': auth_info.get('email')
                    })()
                    self.session = type('Session', (), {
                        'access_token': auth_info.get('access_token'),
                        'refresh_token': auth_info.get('refresh_token'),
                        'expires_at': auth_info.get('expires_at')
                    })()
            
            st.session_state.auth = MockAuth(saved_auth)
            st.session_state.user_email = saved_auth.get('email')
        else:
            st.session_state.auth = None

    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []

def handle_logout():
    st.session_state.auth = None
    st.session_state.session_id = None
    st.session_state.messages = []
    # Xóa auth state từ file
    clear_auth_state()
    st.success("Bạn đã đăng xuất.")
    st.rerun()

def auth_ui():
    st.title("Chào mừng đến với AI Chat")
    st.subheader("Vui lòng đăng nhập hoặc đăng ký để tiếp tục")

    tab1, tab2 = st.tabs(["🔐 Đăng nhập", "📝 Đăng ký"])

    with tab1:
        st.subheader("Đăng nhập")
        with st.form("login_form"):
            login_email = st.text_input("Email", key="login_email")
            login_password = st.text_input("Mật khẩu", type="password", key="login_password")
            login_button = st.form_submit_button("Đăng nhập")

            if login_button:
                if not login_email or not login_password:
                    st.warning("Vui lòng nhập cả email và mật khẩu.")
                else:
                    auth_response = login(login_email, login_password)
                    if auth_response and hasattr(auth_response, 'user') and auth_response.user:
                        token = auth_response.session.access_token 
                        st.session_state.auth = auth_response
                        st.session_state.session_id = generate_session_id()
                        st.session_state.messages = []
                        # Lưu email vào session_state
                        session_storage_set("user_email", login_email)
                        session_storage_set("user_password", login_password) 
                        session_storage_set("access_token", token)  
                        session_storage_set("sessionId", st.session_state.session_id)  
                        st.success("Đăng nhập thành công!")
                        st.rerun()
                    elif auth_response is None:
                        pass
                    else:
                        st.error("Đăng nhập thất bại. Vui lòng kiểm tra thông tin đăng nhập hoặc thử lại.")
                        if hasattr(auth_response, 'error') and auth_response.error:
                             st.error(f"Chi tiết: {auth_response.error.message}")

    with tab2:
        st.subheader("Đăng ký")
        with st.form("signup_form"):
            signup_email = st.text_input("Email", key="signup_email")
            signup_password = st.text_input("Mật khẩu", type="password", key="signup_password")
            signup_confirm_password = st.text_input("Xác nhận mật khẩu", type="password", key="signup_confirm_password")
            signup_button = st.form_submit_button("Đăng ký")

            if signup_button:
                if not signup_email or not signup_password or not signup_confirm_password:
                    st.warning("Vui lòng điền đầy đủ các trường.")
                elif signup_password != signup_confirm_password:
                    st.error("Mật khẩu không khớp.")
                else:
                    signup_response = signup(signup_email, signup_password)
                    if signup_response and hasattr(signup_response, 'user') and signup_response.user:
                        st.success("Đăng ký thành công! Vui lòng kiểm tra email để xác minh (nếu được yêu cầu), sau đó đăng nhập.")
                    elif signup_response is None:
                        pass
                    else:
                        st.error("Đăng ký thất bại. Email có thể đã được sử dụng hoặc mật khẩu quá yếu.")
                        if hasattr(signup_response, 'error') and signup_response.error:
                             st.error(f"Chi tiết: {signup_response.error.message}")

def main():
    st.set_page_config(page_title="AI Chat", layout="wide")
    init_session_state()

    if st.session_state.auth is None or not hasattr(st.session_state.auth, 'user') or not st.session_state.auth.user:
        auth_ui()
    else:
        try:
            col1_main, col2_main, col3_main = st.columns([3, 1, 3])
            with col2_main:
                st.image("logo1.jpg", width=200)
        except FileNotFoundError:
            pass
        except Exception:
            pass

        title_content = rfile("00.xinchao.txt")
        st.markdown(
            f"""<h1 style="text-align: center; font-size: 24px; margin-bottom: 20px;">{title_content}</h1>""",
            unsafe_allow_html=True
        )
        st.markdown(f'''<div class="message-container"><div class="assistant" style=" ">Em Nhi ở đây để tư vấn về "Trợ Lý A.I".
Sếp inbox nội dung cần tư vấn giúp em Nhi nhé !</div></div>''', unsafe_allow_html=True)
        if st.sidebar.button("Đăng xuất", key="logout_button"):
            handle_logout()

        # Inject custom CSS for chat UI
        st.markdown(
            """
            <style>
            .stAppViewBlockContainer  {
                max-width: 1440px;
            }
            .assistant {
                padding: 10px;
                border-radius: 10px;
                max-width: 75%;
                background: none;
                text-align: left;
            }
            .user {
                padding: 10px;
                border-radius: 10px;
                max-width: 75%;
                background: none;
                text-align: right;
                margin-left: auto;
            }
            .stAlert {
                display: none !important;
            }
            h3 {
                display: none;
            }
            .stSidebar {
                width: 150px !important;
                min-width: 140px !important;
            }
            [data-testid="stSidebarHeader"] {
                padding-right: 0px !important;
                }

            [data-testid="stSidebarUserContent"] {
                position: relative;
                bottom: 6%;
                right: -4%;
                padding: 0;
                z-index: 100;
                width: 94px;
            }
            .assistant::before { content: "🤖 "; font-weight: bold; }
            [data-testid="stImageContainer"] img {
                border-radius:0.5rem
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        chat_container = st.container()
        with chat_container:
            for message in st.session_state.messages:
                if message["role"] == "assistant":
                    st.markdown(f'<div class="message-container"><div class="assistant">{message["content"]}</div></div>', unsafe_allow_html=True)
                elif message["role"] == "user":
                    st.markdown(f'<div class="message-container"><div class="user">{message["content"]}</div></div>', unsafe_allow_html=True)

        prompt = st.chat_input("Nhập nội dung cần trao đổi ở đây nhé?")

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with chat_container:
                 st.markdown(f'<div class="message-container"><div class="user">{prompt}</div></div>', unsafe_allow_html=True)

            access_token = ""
            if st.session_state.auth and hasattr(st.session_state.auth, 'session') and st.session_state.auth.session:
                access_token = st.session_state.auth.session.access_token
            else:
                st.error("Không tìm thấy mã thông báo xác thực. Vui lòng đăng nhập lại.")
                return

            with st.spinner("Đang chờ phản hồi từ AI..."):
                llm_response = send_message_to_llm(st.session_state.session_id, prompt, access_token)

            st.session_state.messages.append({"role": "assistant", "content": llm_response})
            with chat_container:
                st.markdown(f'<div class="message-container"><div class="assistant">{llm_response}</div></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if not SUPABASE_KEY:
         try:
            SUPABASE_KEY = rfile("SUPABASE_KEY.txt").strip()
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
         except (FileNotFoundError, KeyError):
            st.error("Không tìm thấy khóa Supabase. Vui lòng cấu hình trong Streamlit secrets hoặc trực tiếp trong script để kiểm thử cục bộ (không khuyến nghị cho production).")
            st.stop()

    if not SUPABASE_KEY:
        st.error("Ứng dụng không thể khởi động: Thiếu Khóa Supabase.")
        st.stop()

    main()
