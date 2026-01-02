import streamlit as st
import streamlit.components.v1 as components
import matplotlib.pyplot as plt
import re
import base64
import json
import os
from io import BytesIO
import datetime
from supabase import create_client, Client
import bcrypt

# --- 0. Supabase接続設定 ---
# 必須: .streamlit/secrets.toml (ローカル) または Streamlit Cloud Secrets (本番)
try:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("エラー: Supabaseへの接続情報が見つかりません。Secrets設定を確認してください。")
    st.stop()

# --- 1. セキュリティ・認証関数 ---

def hash_password(password):
    """パスワードをハッシュ化（暗号化）する"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    """入力パスワードと保存されたハッシュを照合する"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def fetch_user_data(username, password):
    """ログイン処理: ユーザーを検索しデータを取得"""
    try:
        response = supabase.table("users").select("*").eq("username", username).execute()
        if not response.data:
            return None, "ユーザーが見つかりません。"
        
        user_record = response.data[0]
        if check_password(password, user_record["password"]):
            return user_record["data"], "ログインに成功しました。"
        else:
            return None, "パスワードが正しくありません。"
    except Exception as e:
        return None, f"システムエラーが発生しました: {e}"

def create_user(username, password):
    """新規ユーザー登録処理"""
    try:
        # 重複チェック
        response = supabase.table("users").select("username").eq("username", username).execute()
        if response.data:
            return False, "そのユーザー名は既に使用されています。"
        
        # パスワードハッシュ化と登録
        hashed_pw = hash_password(password)
        new_data = {
            "username": username,
            "password": hashed_pw,
            "data": {} # 初期データは空
        }
        supabase.table("users").insert(new_data).execute()
        return True, "ユーザー登録が完了しました。ログインしてください。"
    except Exception as e:
        return False, f"登録エラー: {e}"

def save_user_data_to_db():
    """現在のセッションデータをSupabaseに保存する"""
    if "current_user" not in st.session_state or not st.session_state["current_user"]:
        return

    # 保存対象のデータをまとめる
    data_dict = {
        "saved_songs": st.session_state["saved_songs"],
        "custom_chords": st.session_state["custom_chords"],
        "custom_strokes": st.session_state["custom_strokes"],
        "custom_patterns": st.session_state.get("custom_patterns", {})
    }
    
    try:
        # ログインユーザーのdataカラムを更新
        supabase.table("users").update({"data": data_dict}).eq("username", st.session_state["current_user"]).execute()
        st.toast("クラウドへの保存が完了しました。")
    except Exception as e:
        st.error(f"保存に失敗しました: {e}")

# --- 2. セッション初期化とログイン制御 ---

if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "current_user" not in st.session_state: st.session_state["current_user"] = None

# --- ログイン画面 (未ログイン時) ---
if not st.session_state["logged_in"]:
    st.set_page_config(page_title="弾き語りノート Cloud", page_icon="🎸")
    st.title("🎸 弾き語りノート Cloud")
    st.info("※セキュリティ上の注意：他サイトと同じパスワードは絶対に使用しないでください。")
    
    tab1, tab2 = st.tabs(["🔑 ログイン", "🆕 新規登録"])
    
    with tab1:
        l_user = st.text_input("ユーザー名", key="login_user")
        l_pass = st.text_input("パスワード", type="password", key="login_pass")
        if st.button("ログイン", type="primary"):
            data, msg = fetch_user_data(l_user, l_pass)
            if data is not None:
                st.session_state["logged_in"] = True
                st.session_state["current_user"] = l_user
                # データをセッションに展開
                st.session_state["saved_songs"] = data.get("saved_songs", {})
                st.session_state["custom_chords"] = data.get("custom_chords", {})
                st.session_state["custom_strokes"] = data.get("custom_strokes", {})
                st.session_state["custom_patterns"] = data.get("custom_patterns", {})
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with tab2:
        r_user = st.text_input("ユーザー名 (新規)", key="reg_user")
        r_pass = st.text_input("パスワード (新規)", type="password", key="reg_pass")
        if st.button("登録する"):
            if r_user and r_pass:
                success, msg = create_user(r_user, r_pass)
                if success: st.success(msg)
                else: st.error(msg)
            else:
                st.warning("ユーザー名とパスワードを入力してください。")
    
    st.stop() # ログイン完了までここで処理を停止

# ==========================================
# メインアプリケーション (ログイン後)
# ==========================================

# --- データ定義 ---
DEFAULT_CHORDS = {
    "C": [0, 1, 0, 2, 3, -1], "D": [2, 3, 2, 0, -1, -1], "Dm": [1, 3, 2, 0, -1, -1],
    "E": [0, 0, 1, 2, 2, 0], "Em": [0, 0, 0, 2, 2, 0], "G": [3, 0, 0, 0, 2, 3],
    "A": [0, 2, 2, 2, 0, -1], "Am": [0, 1, 2, 2, 0, -1], "F": [1, 1, 2, 3, 3, 1],
    "B": [2, 4, 4, 4, 2, -1], "Bm": [2, 3, 4, 4, 2, -1],
}
DEFAULT_STROKES = {
    "8beat": ["d", "", "d", "u", "", "u", "d", "u"],
    "16beat": ["d", "", "x", "u", "", "u", "d", "u"],
    "Ballad": ["d", "", "", "", "d", "", "d", "u"],
    "JakaJaka": ["d", "u", "x", "u", "d", "u", "x", "u"],
    "Arpeggio": ["d", ".", ".", ".", ".", ".", ".", "."],
    "Syncopation": ["d", ".", "D", "u", ".", "u", "d", "u"],
}

# --- セッション変数の初期化 ---
if "custom_chords" not in st.session_state: st.session_state["custom_chords"] = {}
if "custom_strokes" not in st.session_state: st.session_state["custom_strokes"] = {}
if "custom_patterns" not in st.session_state: st.session_state["custom_patterns"] = {}
if "saved_songs" not in st.session_state: st.session_state["saved_songs"] = {}
if "editor_text" not in st.session_state:
    st.session_state["editor_text"] = "(例)\n[8beat]\n*桜舞い散る *この道の途中で\n^\n[16beat]\n*君と交わした *約束を抱いて"
if "song_capo" not in st.session_state: st.session_state["song_capo"] = 0
if "song_tags_input" not in st.session_state: st.session_state["song_tags_input"] = []
if "temp_chord" not in st.session_state: st.session_state["temp_chord"] = [0, 1, 0, 2, 3, -1]
if "selected_song_chords" not in st.session_state: st.session_state["selected_song_chords"] = []
if "selected_song_strokes" not in st.session_state: st.session_state["selected_song_strokes"] = []
if "current_pattern_index" not in st.session_state: st.session_state["current_pattern_index"] = 0

# --- 音声・一時ファイル用ヘルパー ---
def save_stroke_audio(name, audio_buffer):
    if not os.path.exists("stroke_sounds"): os.makedirs("stroke_sounds")
    with open(f"stroke_sounds/{name}.wav", "wb") as f: f.write(audio_buffer.read())
def get_stroke_audio_path(name):
    p = f"stroke_sounds/{name}.wav"
    return p if os.path.exists(p) else None
def save_performance_audio(title, audio_buffer):
    if not os.path.exists("recordings"): os.makedirs("recordings")
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[\\/:*?"<>|]+', '', title)
    p = f"recordings/{safe}_{now}.wav"
    with open(p, "wb") as f: f.write(audio_buffer.read())
    return p
def get_performance_history(title):
    if not os.path.exists("recordings"): return []
    safe = re.sub(r'[\\/:*?"<>|]+', '', title)
    files = [f for f in os.listdir("recordings") if f.startswith(safe) and f.endswith(".wav")]
    files.sort(reverse=True)
    return files

# --- ロジック・描画用ヘルパー ---
def get_all_chords():
    d = DEFAULT_CHORDS.copy()
    d.update(st.session_state["custom_chords"])
    return d
def get_all_strokes():
    d = DEFAULT_STROKES.copy()
    d.update(st.session_state["custom_strokes"])
    return d
def normalize_chord_data(d):
    if isinstance(d, dict): return (d.get("positions", [0]*6), d.get("base", 1), d.get("barre", 0), d.get("barre_range", [1, 6]))
    return d, 1, 0, [1, 6]
def normalize_song_data(d):
    if isinstance(d, str): return {"text": d, "capo": 0, "tags": []}
    return {"text": d.get("text",""), "capo": d.get("capo",0), "tags": d.get("tags",[])}
def get_all_tags():
    ts = set(["練習中", "完コピ", "弾き語り"])
    for s in st.session_state["saved_songs"].values():
        ts.update(normalize_song_data(s)["tags"])
    return sorted(list(ts))

# ★重要: 保存処理の統一ラッパー
def save_data_unified():
    save_user_data_to_db()

# --- コールバック関数 ---
def cb_edit_song(t):
    d = normalize_song_data(st.session_state["saved_songs"][t])
    st.session_state["editor_text"] = d["text"]
    st.session_state["song_title_input"] = t
    st.session_state["song_capo"] = d["capo"]
    st.session_state["song_tags_input"] = d["tags"]
    st.session_state["app_mode"] = "📝 歌詞編集"

def cb_quick_save_chord():
    n = st.session_state.get("quick_chord_name")
    if n:
        fr = []
        for i in range(6):
            v = st.session_state.get(f"quick_s{i+1}", "0")
            fr.append(-1 if v=="x" else int(v))
        st.session_state["custom_chords"][n] = {
            "positions": fr, "base": st.session_state.get("quick_chord_base",1),
            "barre": st.session_state.get("quick_chord_barre",0),
            "barre_range": st.session_state.get("quick_chord_range",(1,6))
        }
        save_data_unified()
        st.toast(f"コード「{n}」を保存しました。")

def cb_quick_save_stroke():
    n = st.session_state.get("quick_stroke_name")
    r = st.session_state.get("quick_stroke_input", "")
    p = [x if x!='.' else '' for x in re.findall(r'[duxDU\.]', r)]
    if n and p:
        st.session_state["custom_strokes"][n] = p
        save_data_unified()
        st.toast(f"ストローク「{n}」を保存しました。")

def cb_update_quick_form():
    t = st.session_state.get("quick_load_chord")
    if t and t != "(新規作成)":
        ac = get_all_chords()
        if t in ac:
            ld = normalize_chord_data(ac[t])
            st.session_state["quick_chord_name"] = t
            st.session_state["quick_chord_base"] = ld[1]
            st.session_state["quick_chord_barre"] = ld[2]
            st.session_state["quick_chord_range"] = tuple(ld[3])
            for i in range(6):
                dv = ld[0][i]
                st.session_state[f"quick_s{i+1}"] = "x" if dv==-1 else str(dv)
    else:
        st.session_state["quick_chord_name"] = ""
        st.session_state["quick_chord_base"] = 1
        st.session_state["quick_chord_barre"] = 0
        for i in range(6): st.session_state[f"quick_s{i+1}"] = "0"

def cb_update_quick_stroke_form():
    t = st.session_state.get("quick_load_stroke")
    if t and t != "(新規作成)":
        as_ = get_all_strokes()
        if t in as_:
            st.session_state["quick_stroke_name"] = t
            st.session_state["quick_stroke_input"] = " ".join([p if p!='' else '.' for p in as_[t]])
    else:
        st.session_state["quick_stroke_name"] = ""
        st.session_state["quick_stroke_input"] = ""

# --- 描画関数 ---
def create_chord_base64(chord_name, chord_data, scale=1.0):
    finger_positions, base_fret, barre_fret, barre_range = normalize_chord_data(chord_data)
    fig, ax = plt.subplots(figsize=(1.5 * scale, 1.2 * scale))
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.axis('off'); ax.set_xlim(-0.5, 4.5); ax.set_ylim(6.5, 0.5)
    if barre_fret > 0:
        ax.plot([barre_fret - 0.5, barre_fret - 0.5], [barre_range[0], barre_range[1]], 
                color='black', linewidth=14 * scale, alpha=0.3, solid_capstyle='round')
    for i in range(1, 7): ax.hlines(y=i, xmin=0, xmax=4, color='#555', linewidth=1.0 * scale)
    for i in range(0, 5): 
        is_nut = (i == 0 and base_fret == 1); lw = (3.0 if is_nut else 1.0) * scale
        ax.vlines(x=i, ymin=0.5, ymax=6.5, color='#555', linewidth=lw)
    if base_fret > 1:
        ax.text(0, 0.2, f"{base_fret}fr", fontsize=9*scale, ha='center', va='bottom', color='black', fontweight='bold')
    for string_idx, fret in enumerate(finger_positions):
        string_num = string_idx + 1
        if fret > 0: ax.plot(fret - 0.5, string_num, 'o', color='black', markersize=8 * scale)
        elif fret == 0: ax.plot(-0.2, string_num, 'o', color='white', markeredgecolor='black', markersize=5 * scale)
        elif fret == -1: ax.text(-0.3, string_num, 'x', fontsize=10 * scale, ha='center', va='center', color='black')
    buf = BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)
    return base64.b64encode(buf.getbuffer()).decode("ascii")

def create_stroke_base64(stroke_pattern, scale=1.0):
    if not stroke_pattern: return ""
    steps = len(stroke_pattern)
    fig, ax = plt.subplots(figsize=(0.2 * steps * scale, 0.6 * scale)) 
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.axis('off'); ax.set_xlim(-0.5, steps - 0.5); ax.set_ylim(-0.2, 1.2)
    for i, note in enumerate(stroke_pattern):
        x = i
        if note == "d": ax.arrow(x, 1.0, 0, -0.8, head_width=0.5, head_length=0.25, fc='black', ec='black')
        elif note == "u": ax.arrow(x, 0.0, 0, 0.8, head_width=0.5, head_length=0.25, fc='black', ec='black')
        elif note == "D": ax.arrow(x, 1.0, 0, -0.8, head_width=0.5, head_length=0.25, fc='#ccc', ec='#999')
        elif note == "U": ax.arrow(x, 0.0, 0, 0.8, head_width=0.5, head_length=0.25, fc='#ccc', ec='#999')
        elif note.lower() == "x": ax.text(x, 0.5, "×", fontsize=20*scale, ha='center', va='center', fontweight='bold', color='#333')
    buf = BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)
    return base64.b64encode(buf.getbuffer()).decode("ascii")

def generate_song_html(text, all_chords, all_strokes):
    html_parts = []
    html_parts.append('<div style="font-family: sans-serif; padding: 10px;">')
    current_stroke_name = None 
    lines = text.split('\n')
    for line in lines:
        html_parts.append('<div style="display: flex; flex-wrap: wrap; align-items: flex-end; margin-bottom: 20px; min-height: 100px;">')
        parts = re.split(r'(\[.*?\])', line)
        pending_chord = None
        for part in parts:
            if not part: continue
            if part.startswith('[') and part.endswith(']'):
                tag_content = part[1:-1]
                if tag_content in all_strokes or tag_content == "stop":
                    current_stroke_name = tag_content if tag_content != "stop" else None
                    continue
                elif tag_content in all_chords:
                    if pending_chord:
                        b64_chord = create_chord_base64(pending_chord, all_chords[pending_chord])
                        if current_stroke_name and current_stroke_name in all_strokes:
                            b64_stroke = create_stroke_base64(all_strokes[current_stroke_name], scale=0.8)
                            stroke_div = f'<img src="data:image/png;base64,{b64_stroke}" style="height:25px; object-fit:contain; display:block; margin-left: 2px;">'
                        else: stroke_div = '<div style="height:25px;"></div>'
                        html_parts.append(f'<div style="display: flex; flex-direction: column; align-items: flex-start; margin-right: 8px;"><span style="font-weight:bold; color:#e74c3c; font-size:0.9em; margin-bottom:2px; margin-left:2px;">{pending_chord}</span><img src="data:image/png;base64,{b64_chord}" style="width:40px; display:block; margin-bottom:20px;">{stroke_div}<div style="height: 1.2em;">&nbsp;</div></div>')
                    pending_chord = tag_content
            else:
                lyric_text = part
                if pending_chord:
                    b64_chord = create_chord_base64(pending_chord, all_chords[pending_chord])
                    if current_stroke_name and current_stroke_name in all_strokes:
                        b64_stroke = create_stroke_base64(all_strokes[current_stroke_name], scale=0.8)
                        stroke_div = f'<img src="data:image/png;base64,{b64_stroke}" style="height:25px; object-fit:contain; display:block; margin-left: 2px;">'
                    else: stroke_div = '<div style="height:25px;"></div>'
                    html_parts.append(f'<div style="display: flex; flex-direction: column; align-items: flex-start; margin-right: 2px;"><span style="font-weight:bold; color:#e74c3c; font-size:0.9em; margin-bottom:2px; margin-left:2px;">{pending_chord}</span><img src="data:image/png;base64,{b64_chord}" style="width:40px; display:block; margin-bottom:20px;">{stroke_div}<div style="font-size: 1.1em; border-bottom: 1px solid #eee; white-space: nowrap; height: 1.5em; margin-top: 5px;">{lyric_text}</div></div>')
                    pending_chord = None
                else:
                    html_parts.append(f'<div style="display: flex; flex-direction: column; justify-content: flex-end; margin-right: 2px;"><div style="height:20px;"></div><div style="width:40px; height:0px;"></div><div style="height:20px;"></div><div style="height:25px;"></div><div style="font-size: 1.1em; border-bottom: 1px solid #eee; white-space: nowrap; height: 1.5em; margin-top: 5px;">{lyric_text}</div></div>')
        if pending_chord:
            b64_chord = create_chord_base64(pending_chord, all_chords[pending_chord])
            if current_stroke_name and current_stroke_name in all_strokes:
                b64_stroke = create_stroke_base64(all_strokes[current_stroke_name], scale=0.8)
                stroke_div = f'<img src="data:image/png;base64,{b64_stroke}" style="height:25px; object-fit:contain; display:block; margin-left: 2px;">'
            else: stroke_div = '<div style="height:25px;"></div>'
            html_parts.append(f'<div style="display: flex; flex-direction: column; align-items: flex-start; margin-right: 8px;"><span style="font-weight:bold; color:#e74c3c; font-size:0.9em; margin-bottom:2px; margin-left:2px;">{pending_chord}</span><img src="data:image/png;base64,{b64_chord}" style="width:40px; display:block; margin-bottom:20px;">{stroke_div}<div style="height: 1.5em; border-bottom: 1px solid transparent;">&nbsp;</div></div>')
        html_parts.append('</div>')
    html_parts.append('</div>')
    return "".join(html_parts)

def view_song_with_player(html_content, title):
    player_html = f"""
    <!DOCTYPE html><html><head><style>
    body {{ margin: 0; padding: 0; font-family: sans-serif; background: #fff; }}
    #song-container {{ height: 70vh; overflow-y: auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px; background-color: #fff; margin-bottom: 10px; scroll-behavior: smooth; }}
    #controls {{ display: flex; gap: 10px; padding: 10px; background: #f0f2f6; border-radius: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; }}
    .btn {{ padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; color: white; }}
    .btn-scroll {{ background-color: #333; }}
    .btn-metro {{ background-color: #ff4b4b; }}
    .setting-group {{ display: flex; align-items: center; gap: 5px; font-size: 12px; color: #555; background:white; padding:5px; border-radius:5px; }}
    </style></head><body>
    <div id="controls">
        <div class="setting-group"><button id="btn-scroll" class="btn btn-scroll">📜 Scroll</button><label>Spd:</label><input type="range" id="scroll-speed" min="1" max="50" value="10" style="width:80px;"></div>
        <div class="setting-group"><button id="btn-metro" class="btn btn-metro">⏱️ <span id="bpm-val">120</span></button><input type="range" id="metro-bpm" min="40" max="240" value="120" style="width:80px;"><label>Vol:</label><input type="range" id="metro-vol" min="0" max="100" value="50" style="width:50px;"></div>
    </div>
    <div id="song-container"><h2 style="margin-top:0;">{title}</h2>{html_content}<div style="height: 300px;"></div></div>
    <script>
    const sc = document.getElementById('song-container'); const bs = document.getElementById('btn-scroll'); const sp = document.getElementById('scroll-speed');
    let isS=false; let sI;
    
    // ↓ ここを修正しました ({{ と }})
    bs.addEventListener('click',()=>{{
        isS=!isS; if(isS){{bs.innerText="⏹️ Stop";bs.style.backgroundColor="#ff4b4b";startS();}}else{{bs.innerText="📜 Scroll";bs.style.backgroundColor="#333";clearInterval(sI);}}
    }});
    
    // ↓ ここも修正しました
    sp.addEventListener('input',()=>{{if(isS)startS();}});
    
    function startS(){{clearInterval(sI);const s=51-parseInt(sp.value);sI=setInterval(()=>{{sc.scrollTop+=1;}},s*2);}}
    
    const ac=new(window.AudioContext||window.webkitAudioContext)(); let isP=false; let bpm=120; let nT=0.0; let tID; let vol=0.5;
    const bm=document.getElementById('btn-metro'); const bsld=document.getElementById('metro-bpm'); const bdis=document.getElementById('bpm-val'); const vsld=document.getElementById('metro-vol');
    
    function play(t){{const o=ac.createOscillator();const g=ac.createGain();o.connect(g);g.connect(ac.destination);o.type='square';o.frequency.value=1000;g.gain.setValueAtTime(vol*0.3,t);g.gain.exponentialRampToValueAtTime(0.001,t+0.1);o.start(t);o.stop(t+0.1);}}
    function sch(){{while(nT<ac.currentTime+0.1){{play(nT);nT+=60.0/bpm;}}tID=window.setTimeout(sch,25);}}
    
    // ↓ ここも修正しました
    bm.addEventListener('click',()=>{{
        if(ac.state==='suspended')ac.resume(); isP=!isP; if(isP){{bm.style.backgroundColor="#333";nT=ac.currentTime;sch();}}else{{bm.style.backgroundColor="#ff4b4b";window.clearTimeout(tID);}}
    }});
    
    bsld.addEventListener('input',function(){{bpm=this.value;bdis.innerText=bpm;}}); vsld.addEventListener('input',function(){{vol=this.value/100;}});
    </script></body></html>
    """
    components.html(player_html, height=700, scrolling=False)

# --- その他のアクション ---
def insert_chord(name):
    ct = st.session_state["editor_text"]
    st.session_state["editor_text"] = ct.replace("*", f"[{name}]", 1) if "*" in ct else ct + f" [{name}]"
def insert_stroke(name):
    ct = st.session_state["editor_text"]
    st.session_state["editor_text"] = ct.replace("^", f"[{name}]", 1) if "^" in ct else ct + f"\n[{name}]\n"
def register_chord():
    n = st.session_state.new_chord_name
    fr = st.session_state["temp_chord"]
    b = st.session_state.get("new_chord_base", 1)
    br = st.session_state.get("new_chord_barre", 0)
    brr = st.session_state.get("new_chord_barre_range", (1, 6))
    if n:
        st.session_state["custom_chords"][n] = {"positions": fr, "base": b, "barre": br, "barre_range": brr}
        save_data_unified()
        st.session_state["new_chord_name"] = "" 
        st.toast(f"コード「{n}」を登録しました。")
def register_stroke():
    n = st.session_state.new_stroke_name
    r = st.session_state.new_stroke_input
    p = [x if x != '.' else '' for x in re.findall(r'[duxDU\.]', r)]
    if n and p:
        st.session_state["custom_strokes"][n] = p
        save_data_unified()
        st.session_state["new_stroke_name"] = "" 
        st.session_state["new_stroke_input"] = "" 
        st.toast(f"ストローク「{n}」を登録しました。")
def save_song():
    t = st.session_state.song_title_input
    if t:
        ft = list(st.session_state.get("song_tags_input", []))
        nt = st.session_state.get("new_tag_text", "")
        if nt and nt not in ft: ft.append(nt)
        st.session_state["saved_songs"][t] = {
            "text": st.session_state["editor_text"], 
            "capo": st.session_state.song_capo,
            "tags": ft
        }
        save_data_unified()
        st.session_state["new_tag_text"] = "" 
        st.toast(f"曲「{t}」を保存しました。")
def update_string_state():
    nf = []
    for i in range(1, 7):
        v = st.session_state[f"s{i}_radio"]
        nf.append(-1 if v == "x" else int(v))
    st.session_state["temp_chord"] = nf

# --- ページ設定 & UI ---
st.set_page_config(layout="wide", page_title="弾き語りノート", page_icon="🎸")
st.title("🎸 弾き語りノート")

ALL_CHORDS = get_all_chords()
ALL_STROKES = get_all_strokes()

with st.sidebar:
    st.header("メニュー")
    if st.session_state["current_user"]:
        st.caption("☁️ Cloud Mode")
        st.write(f"👤 **{st.session_state['current_user']}**")
        if st.button("ログアウト"):
            st.session_state["logged_in"] = False
            st.session_state["current_user"] = None
            st.rerun()
        st.divider()

    mode = st.radio("モード", ["📝 歌詞編集", "📂 曲管理・閲覧", "➕ コード登録", "🌊 ストローク登録", "🎼 パターン登録", "🔧 登録データ管理"], key="app_mode")
    st.divider()

    if mode == "📝 歌詞編集":
        st.subheader("保存")
        c1, c2 = st.columns([2.5, 1])
        with c1: st.text_input("タイトル", key="song_title_input")
        with c2: st.number_input("Capo", min_value=0, max_value=12, key="song_capo")
        st.multiselect("タグ", get_all_tags(), key="song_tags_input")
        st.text_input("新規タグ", key="new_tag_text")
        st.button("この内容を保存", on_click=save_song, type="primary")

if mode == "📝 歌詞編集":
    col_edit, col_view = st.columns([1, 1.5])
    with col_edit:
        st.subheader("1. 編集")
        with st.expander("🆕 クイック編集・登録 (コード/ストローク/パターン)"):
            q_tab_c, q_tab_s, q_tab_p = st.tabs(["🎸 コード", "🌊 ストローク", "🎼 パターン"])
            with q_tab_c:
                all_c = sorted(list(ALL_CHORDS.keys()))
                st.selectbox("既存コード読込", ["(新規作成)"] + all_c, key="quick_load_chord", on_change=cb_update_quick_form)
                qc_prev, qc_meta, qc_str = st.columns([1, 1, 1.5])
                with qc_meta:
                    qn = st.text_input("コード名", key="quick_chord_name")
                    qb = st.number_input("開始Fr", 1, 12, 1, key="quick_chord_base")
                    qbar = st.selectbox("セーハ", [0,1,2,3,4], key="quick_chord_barre")
                    q_rng = (1, 6)
                    if qbar > 0: q_rng = st.slider("セーハ範囲", 1, 6, (1,6), key="quick_chord_range")
                with qc_str:
                    q_frets = []
                    for i in range(6):
                        val_s = st.selectbox(f"{i+1}弦", ["x","0","1","2","3","4"], index=1, key=f"quick_s{i+1}", label_visibility="collapsed")
                        q_frets.append(-1 if val_s=="x" else int(val_s))
                with qc_prev:
                    st.write("Preview")
                    prev_data = {"positions": q_frets, "base": qb, "barre": qbar, "barre_range": q_rng}
                    st.markdown(f'<img src="data:image/png;base64,{create_chord_base64(qn, prev_data, scale=1.8)}" style="max-width:100%;">', unsafe_allow_html=True)
                st.button("保存 / 更新", key="btn_quick_save_c", on_click=cb_quick_save_chord)
            with q_tab_s:
                all_s = sorted(list(ALL_STROKES.keys()))
                st.selectbox("既存ストローク読込", ["(新規作成)"] + all_s, key="quick_load_stroke", on_change=cb_update_quick_stroke_form)
                qs_prev, qs_inp = st.columns([1, 1])
                with qs_inp:
                    sn = st.text_input("ストローク名", key="quick_stroke_name")
                    si = st.text_input("パターン (d u x D U .)", key="quick_stroke_input", help="d,u,x,D,U が使えます")
                with qs_prev:
                    st.write("Preview")
                    prev_pat = [p if p!='.' else '' for p in re.findall(r'[duxDU\.]', si)]
                    if prev_pat: st.markdown(f'<img src="data:image/png;base64,{create_stroke_base64(prev_pat, scale=1.5)}" style="max-width:100%;">', unsafe_allow_html=True)
                st.button("保存 / 更新", key="btn_quick_save_s", on_click=cb_quick_save_stroke)
            with q_tab_p:
                st.markdown("##### 🎼 パターン作成")
                pn = st.text_input("パターン名", placeholder="例：カノン進行")
                pc = st.text_input("コード順 (カンマ区切り)", placeholder="C, G, Am, Em")
                ps = st.text_input("ストローク順 (カンマ区切り・任意)", placeholder="8beat, 8beat...")
                if st.button("パターンを保存", key="btn_save_pat_quick", type="primary"):
                    if pn and pc:
                        cl = [c.strip() for c in pc.split(',') if c.strip()]
                        sl = [s.strip() for s in ps.split(',') if s.strip()]
                        st.session_state["custom_patterns"][pn] = {"chords": cl, "strums": sl}
                        save_data_unified()
                        st.success(f"パターン「{pn}」を保存しました。")
                        st.rerun()
                    else: st.error("名前とコードは必須項目です。")
                st.divider()
                st.markdown("##### 📜 登録済みパターンリスト")
                if st.session_state["custom_patterns"]:
                    for name, dat in list(st.session_state["custom_patterns"].items()):
                        c_p1, c_p2 = st.columns([3, 1])
                        with c_p1: st.write(f"**{name}**: {', '.join(dat['chords'])}")
                        with c_p2:
                            if st.button("削除", key=f"del_pat_q_{name}"):
                                del st.session_state["custom_patterns"][name]
                                save_data_unified()
                                st.rerun()
                else: st.caption("登録されたパターンはありません。")
        st.divider()
        st.caption("`*` はコード、`^` はストロークに置換されます。")
        def on_text_change(): st.session_state["editor_text"] = st.session_state["editor_key"]
        st.text_area("歌詞入力", key="editor_key", height=400, value=st.session_state["editor_text"], on_change=on_text_change)
        if st.session_state["custom_patterns"]:
            st.write("▼ パターンから入力")
            p_container = st.container(border=True)
            with p_container:
                p_options = list(st.session_state["custom_patterns"].keys())
                sel_p = st.selectbox("パターン選択", p_options, label_visibility="collapsed")
                if sel_p:
                    curr_pat = st.session_state["custom_patterns"][sel_p]
                    idx = st.session_state["current_pattern_index"]
                    next_c_name = curr_pat['chords'][idx % len(curr_pat['chords'])] if curr_pat['chords'] else "なし"
                    next_s_name = curr_pat['strums'][idx % len(curr_pat['strums'])] if curr_pat['strums'] else "なし"
                    bc1, bc2, bc3 = st.columns(3)
                    with bc1:
                        if st.button(f"次へ ({next_c_name})", use_container_width=True):
                            st.session_state["editor_text"] += f" [{next_c_name}]"
                            st.session_state["current_pattern_index"] += 1
                            st.rerun()
                    with bc2:
                        if curr_pat['strums']:
                            if st.button(f"ストローク ({next_s_name})", use_container_width=True):
                                st.session_state["editor_text"] += f"\n[{next_s_name}]\n"
                                st.rerun()
                        else: st.button("設定なし", disabled=True, use_container_width=True)
                    with bc3:
                        if st.button("リセット", use_container_width=True):
                            st.session_state["current_pattern_index"] = 0
                            st.rerun()
                    if st.button("📋 パターンを一括入力", use_container_width=True):
                         full_pattern_str = "".join([f" [{c}]" for c in curr_pat['chords']])
                         st.session_state["editor_text"] += full_pattern_str
                         st.rerun()
                    st.caption(f"現在の位置: {idx + 1}番目 (次は「{next_c_name}」です)")
        else: st.info("💡 「クイック編集・登録」の「パターン」タブでパターンを作成すると、ここに入力ボタンが表示されます。")
        st.write("▼ ストローク挿入")
        if not st.session_state["selected_song_strokes"]:
            ds = ["8beat", "16beat", "Ballad"]
            st.session_state["selected_song_strokes"] = [s for s in ds if s in ALL_STROKES]
        sel_s = st.multiselect("ストローク選択", options=list(ALL_STROKES.keys())+["stop"], default=st.session_state["selected_song_strokes"], key="stroke_selector")
        st.session_state["selected_song_strokes"] = sel_s
        if sel_s:
            cols = st.columns(5)
            for i, s in enumerate(sel_s):
                with cols[i%5]: st.button(f"🌊 {s}", on_click=insert_stroke, args=(s,), use_container_width=True)
        st.divider()
        st.write("▼ コード挿入")
        if not st.session_state["selected_song_chords"]:
            dc = ["C", "G", "Am", "F", "Em", "Dm"]
            st.session_state["selected_song_chords"] = [c for c in dc if c in ALL_CHORDS]
        sel_c = st.multiselect("コード選択", options=list(ALL_CHORDS.keys()), default=st.session_state["selected_song_chords"], key="chord_selector")
        st.session_state["selected_song_chords"] = sel_c
        if sel_c:
            cols = st.columns(6)
            for i, c in enumerate(sel_c):
                with cols[i%6]:
                    lbl = f"★{c}" if c in st.session_state["custom_chords"] else c
                    st.button(lbl, on_click=insert_chord, args=(c,), use_container_width=True)
    with col_view:
        st.subheader("2. プレビュー")
        capo = st.session_state.song_capo
        t = st.session_state.get('song_title_input', 'No Title')
        c_txt = f" (Capo: {capo})" if capo > 0 else ""
        tags_display = ""
        current_tags = st.session_state.get("song_tags_input", [])
        if current_tags:
            tags_html = "".join([f"<span style='background:#eee;padding:2px 6px;margin-right:4px;border-radius:4px;font-size:0.8em;color:#555;'>{tag}</span>" for tag in current_tags])
            tags_display = f"<div style='margin-top:4px;'>{tags_html}</div>"
        st.markdown(f"**Title: {t}{c_txt}**", unsafe_allow_html=True)
        st.markdown(tags_display, unsafe_allow_html=True)
        st.divider()
        st.markdown(generate_song_html(st.session_state["editor_text"], ALL_CHORDS, ALL_STROKES), unsafe_allow_html=True)

elif mode == "📂 曲管理・閲覧":
    st.markdown("## 📂 曲管理・閲覧")
    if st.session_state["saved_songs"]:
        st.caption("保存済みの曲を検索・選択・録音できます。")
        col_filter, col_select = st.columns([1, 1.5])
        with col_filter:
            all_tags_view = get_all_tags()
            filter_tags = st.multiselect("🏷️ タグで絞り込み", all_tags_view, key="view_filter_tags")
        all_songs = list(st.session_state["saved_songs"].keys())
        if filter_tags:
            filtered_songs = []
            for s in all_songs:
                s_tags = set(normalize_song_data(st.session_state["saved_songs"][s])["tags"])
                if set(filter_tags).issubset(s_tags): filtered_songs.append(s)
            song_candidates = filtered_songs
        else: song_candidates = all_songs
        with col_select:
            if song_candidates: selected_title = st.selectbox("🎵 曲を選択", song_candidates, key="selected_song_view")
            else:
                selected_title = None
                st.warning("条件に合う曲がありません")
        if selected_title:
            song_data = normalize_song_data(st.session_state["saved_songs"][selected_title])
            view_text = song_data["text"]
            view_capo = song_data["capo"]
            view_tags = song_data["tags"]
            st.write("")
            col_act1, col_act2, col_dummy = st.columns([1, 1, 2])
            with col_act1: st.button("✏️ 編集する", use_container_width=True, key=f"btn_edit_{selected_title}", on_click=cb_edit_song, args=(selected_title,))
            with col_act2:
                if st.button("🗑️ 削除する", type="secondary", use_container_width=True, key=f"btn_del_{selected_title}"):
                    del st.session_state["saved_songs"][selected_title]
                    save_data_unified()
                    st.success(f"「{selected_title}」を削除しました。")
                    st.rerun()
            st.divider()
            with st.expander("🎙️ この曲を録音する / 履歴を見る", expanded=False):
                r_col1, r_col2 = st.columns([1, 1])
                with r_col1:
                    st.markdown("##### 新しく録音")
                    st.caption("録音ボタンを押して演奏してください。完了後、送信ボタンで保存されます。")
                    rec_audio = st.audio_input("演奏を録音", key=f"rec_perf_{selected_title}")
                    if rec_audio:
                        save_path = save_performance_audio(selected_title, rec_audio)
                        st.success("録音が完了しました。履歴に追加されました。")
                with r_col2:
                    st.markdown("##### 📜 録音履歴")
                    history_files = get_performance_history(selected_title)
                    if history_files:
                        for h_file in history_files:
                            try:
                                time_part = h_file.replace(".wav", "").split("_")[-2:]
                                display_date = f"{time_part[0][:4]}/{time_part[0][4:6]}/{time_part[0][6:]} {time_part[1][:2]}:{time_part[1][2:4]}"
                            except: display_date = h_file
                            with st.container(border=True):
                                st.write(f"📅 {display_date}")
                                st.audio(f"recordings/{h_file}")
                                if st.button("削除", key=f"del_rec_{h_file}"):
                                    os.remove(f"recordings/{h_file}")
                                    st.rerun()
                    else: st.info("録音データはありません。")
            capo_disp = f" <span style='font-size:0.8em; color:#555; font-weight:normal; margin-left:10px;'>Capo: {view_capo}</span>" if view_capo > 0 else ""
            tags_html = ""
            if view_tags:
                tags_span = "".join([f"<span style='background:#eee;padding:2px 6px;margin-right:4px;border-radius:4px;font-size:0.6em;color:#555;vertical-align:middle;'>{tag}</span>" for tag in view_tags])
                tags_html = f"&nbsp;&nbsp;{tags_span}"
            st.markdown(f"### {selected_title}{capo_disp}{tags_html}", unsafe_allow_html=True)
            html_content = generate_song_html(view_text, ALL_CHORDS, ALL_STROKES)
            view_song_with_player(html_content, selected_title)
    else: st.info("保存された曲がありません。まずは「📝 歌詞編集」で曲を作成・保存してください。")

elif mode == "➕ コード登録":
    st.subheader("カスタムコード作成")
    cp, cc = st.columns([1, 1.5])
    pn = st.session_state.get("new_chord_name", "New Chord")
    if not pn: pn = "New Chord"
    p_dat = {"positions": st.session_state["temp_chord"], "base": st.session_state.get("new_chord_base", 1), 
             "barre": st.session_state.get("new_chord_barre", 0), "barre_range": st.session_state.get("new_chord_barre_range", (1,6))}
    with cp:
        st.markdown("### Preview")
        st.markdown(f"""<div style="border:2px solid #ddd;padding:20px;text-align:center;background:white;"><div style="font-size:24px;font-weight:bold;margin-bottom:10px;color:#333;">{pn}</div><img src="data:image/png;base64,{create_chord_base64(pn, p_dat, 2.5)}" style="max-width:100%;"></div>""", unsafe_allow_html=True)
        st.write(""); st.text_input("コード名", key="new_chord_name")
        st.button("登録", on_click=register_chord, type="primary")
    with cc:
        c1, c2 = st.columns(2)
        with c1: st.number_input("開始Fr", 1, 12, 1, key="new_chord_base")
        with c2: st.selectbox("セーハ", [0,1,2,3,4], key="new_chord_barre")
        if st.session_state["new_chord_barre"] > 0: st.slider("範囲", 1, 6, (1,6), key="new_chord_barre_range")
        st.divider(); st.markdown("### Strings")
        for i in range(6):
            with st.container(border=True):
                st.markdown(f"**{i+1}弦**")
                st.radio(f"s{i+1}", ["x","0","1","2","3","4"], index=(st.session_state["temp_chord"][i]+1) if st.session_state["temp_chord"][i]!=-1 else 0, key=f"s{i+1}_radio", horizontal=True, on_change=update_string_state, label_visibility="collapsed")

elif mode == "🌊 ストローク登録":
    st.subheader("カスタムストローク作成"); c1, c2 = st.columns([1,1])
    with c1:
        st.text_input("名前", key="new_stroke_name")
        st.text_input("パターン (d u x D U .)", key="new_stroke_input", help="d,u,x,D,U が使えます")
        st.write("🎙️ お手本を録音 (任意)")
        audio_val = st.audio_input("録音開始", key="rec_new_stroke")
        def register_stroke_action():
            name = st.session_state.new_stroke_name
            raw_str = st.session_state.new_stroke_input
            pat = [p if p != '.' else '' for p in re.findall(r'[duxDU\.]', raw_str)]
            if name and pat:
                st.session_state["custom_strokes"][name] = pat
                if audio_val:
                    audio_val.seek(0)
                    save_stroke_audio(name, audio_val)
                save_data_unified()
                st.session_state["new_stroke_name"] = "" 
                st.session_state["new_stroke_input"] = "" 
                st.toast(f"ストローク「{name}」を登録しました。")
            else: st.error("名前とパターンを入力してください。")
        st.button("登録", on_click=register_stroke_action, type="primary")
    with c2:
        st.markdown("Preview")
        si = st.session_state.get("new_stroke_input", "")
        pt = [p if p!='.' else '' for p in re.findall(r'[duxDU\.]', si)]
        if pt: st.markdown(f'<img src="data:image/png;base64,{create_stroke_base64(pt, 2.0)}">', unsafe_allow_html=True)

elif mode == "🎼 パターン登録":
    st.subheader("🎼 パターン作成工房")
    st.caption("よく使うコード進行やストローク進行を登録することで、入力作業を効率化できます。")
    c_pat, c_list = st.columns([1, 1])
    with c_pat:
        with st.container(border=True):
            st.markdown("##### 新しいパターンを作成")
            pn = st.text_input("パターン名", placeholder="例：カノン進行、サビ、Aメロ")
            pc = st.text_input("コードの順番 (カンマ区切り)", placeholder="C, G, Am, Em, F, C, F, G")
            ps = st.text_input("ストロークの順番 (カンマ区切り・任意)", placeholder="8beat, 8beat, 16beat...")
            if st.button("パターンを保存", type="primary"):
                if pn and pc:
                    cl = [c.strip() for c in pc.split(',') if c.strip()]
                    sl = [s.strip() for s in ps.split(',') if s.strip()]
                    st.session_state["custom_patterns"][pn] = {"chords": cl, "strums": sl}
                    save_data_unified()
                    st.success(f"パターン「{pn}」を保存しました。")
                else: st.error("名前とコードは必須項目です。")
    with c_list:
        st.markdown("##### 📜 登録済みパターン")
        if st.session_state["custom_patterns"]:
            for name, dat in list(st.session_state["custom_patterns"].items()):
                with st.expander(f"🎼 {name}"):
                    st.write(f"**コード:** {', '.join(dat['chords'])}")
                    if dat['strums']: st.write(f"**ストローク:** {', '.join(dat['strums'])}")
                    if st.button("削除", key=f"del_pat_{name}"):
                        del st.session_state["custom_patterns"][name]
                        save_data_unified()
                        st.rerun()
        else: st.info("登録されたパターンはありません。")

elif mode == "🔧 登録データ管理":
    st.subheader("登録データ管理"); t1, t2 = st.tabs(["🎸 コード", "🌊 ストローク"])
    with t1:
        sel = st.selectbox("編集コード選択", sorted(list(ALL_CHORDS.keys())))
        if sel:
            st.divider(); cd = ALL_CHORDS[sel]; ld = normalize_chord_data(cd)
            is_def = sel in DEFAULT_CHORDS; is_cus = sel in st.session_state["custom_chords"]
            st.markdown(f"ステータス: {'🔵 上書き中' if is_cus and is_def else ('🟢 オリジナル' if is_cus else '⚪ デフォルト')}")
            mc1, mc2 = st.columns([1, 1.5])
            with mc2:
                nn = st.text_input("名前", value=sel, key=f"mn_{sel}")
                mb = st.number_input("開始Fr", 1, 12, ld[1], key=f"mb_{sel}")
                mbr = st.selectbox("セーハ", [0,1,2,3,4], index=ld[2] if ld[2]<=4 else 0, key=f"mbr_{sel}")
                mrg = tuple(ld[3])
                if mbr > 0: mrg = st.slider("範囲", 1, 6, mrg, key=f"mrg_{sel}")
                npos = []
                st.write("弦設定")
                cols = st.columns(6)
                for i in range(6):
                    d = ld[0][i]; idx = d+1 if d!=-1 else 0
                    with cols[i]:
                        v = st.selectbox(f"{i+1}", ["x","0","1","2","3","4"], index=idx, key=f"ms_{sel}_{i}", label_visibility="collapsed")
                        npos.append(-1 if v=="x" else int(v))
            with mc1:
                prev = {"positions":npos, "base":mb, "barre":mbr, "barre_range":mrg}
                st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{create_chord_base64(nn, prev, 2.0)}"></div>', unsafe_allow_html=True)
            with mc2:
                c_b1, c_b2 = st.columns(2)
                with c_b1:
                    def save_manage_chord():
                        st.session_state["custom_chords"][nn] = prev
                        if nn != sel and sel in st.session_state["custom_chords"]: del st.session_state["custom_chords"][sel]
                        save_data_unified()
                        st.toast("更新しました。")
                    st.button("更新", key=f"btn_upd_{sel}", type="primary", on_click=save_manage_chord)
                with c_b2:
                    if is_cus:
                        def del_manage_chord():
                            del st.session_state["custom_chords"][sel]
                            save_data_unified()
                            st.toast("削除しました。")
                        st.button("削除/初期化", key=f"btn_del_{sel}", type="secondary", on_click=del_manage_chord)
                    else: st.button("削除不可", disabled=True, key=f"dis_c_{sel}")
    with t2:
        sels = st.selectbox("編集ストローク選択", sorted(list(ALL_STROKES.keys())))
        if sels:
            st.divider(); sd = ALL_STROKES[sels]
            isc_s = sels in st.session_state["custom_strokes"]; isd_s = sels in DEFAULT_STROKES
            st.markdown(f"ステータス: {'🔵 上書き中' if isc_s and isd_s else ('🟢 オリジナル' if isc_s else '⚪ デフォルト')}")
            ms1, ms2 = st.columns([1, 1])
            with ms2:
                nns = st.text_input("名前", value=sels, key=f"mns_{sels}")
                ins = st.text_input("パターン", value=" ".join([p if p!='' else '.' for p in sd]), key=f"mis_{sels}")
                pat = [p if p!='.' else '' for p in re.findall(r'[duxDU\.]', ins)]
                st.divider()
                st.markdown("#### 🎙️ お手本サウンド")
                exist_audio = get_stroke_audio_path(sels)
                if exist_audio:
                    st.audio(exist_audio)
                    if st.button("🗑️ 音声を削除", key=f"del_audio_{sels}", type="secondary"):
                        os.remove(exist_audio)
                        st.toast(f"「{sels}」の音声を削除しました。")
                        st.rerun()
                else: st.info("録音データはありません。")
                new_audio = st.audio_input("新しく録音する", key=f"rec_update_{sels}")
            with ms1:
                st.markdown(f'<div style="text-align:center;margin-top:20px;"><img src="data:image/png;base64,{create_stroke_base64(pat, 2.0)}"></div>', unsafe_allow_html=True)
            with ms2:
                sb1, sb2 = st.columns(2)
                with sb1:
                    def save_manage_stroke():
                        if pat:
                            st.session_state["custom_strokes"][nns] = pat
                            if nns != sels and sels in st.session_state["custom_strokes"]: 
                                del st.session_state["custom_strokes"][sels]
                            if new_audio: save_stroke_audio(nns, new_audio)
                            save_data_unified()
                            st.toast("更新しました。")
                    st.button("更新", key=f"btn_upds_{sels}", type="primary", on_click=save_manage_stroke)
                with sb2:
                    if isc_s:
                        def del_manage_stroke():
                            del st.session_state["custom_strokes"][sels]
                            save_data_unified()
                            st.toast("削除しました。")
                        st.button("削除/初期化", key=f"btn_dels_{sels}", type="secondary", on_click=del_manage_stroke)
                    else: st.button("削除不可", disabled=True, key=f"dis_s_{sels}")