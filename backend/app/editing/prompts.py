"""編集提案プロンプト.

動画情報（長さ）と台本を元に、AIへ編集案を JSON で出力させる。
"""
from __future__ import annotations

from .models import SuggestRequest

_JSON_SHAPE = """{
  "cuts": [
    {"start_sec": 12.0, "end_sec": 15.5, "reason": "無音・間延び"}
  ],
  "telops": [
    {"time_sec": 3.0, "text": "画面に出すテロップ"}
  ],
  "bgm_suggestions": ["明るいローファイ", "疾走感のあるEDM"],
  "tempo_tips": ["冒頭5秒を短くして結論を先に見せる"],
  "short_plan": {
    "target_duration_sec": 30,
    "vertical": true,
    "segments": [{"start_sec": 40.0, "end_sec": 70.0, "reason": "一番の見せ場"}]
  }
}"""

SYSTEM_PROMPT = (
    "あなたはプロの動画編集者です。"
    "動画の長さと台本をもとに、視聴維持率を高める編集案を提案します。\n\n"
    "出力は必ず次の JSON 形式のみで返してください。"
    "説明文やコードフェンス(```)は付けず、JSON オブジェクトだけを出力します。\n"
    f"{_JSON_SHAPE}\n\n"
    "ルール:\n"
    "- タイムコード(start_sec/end_sec/time_sec)は動画の長さの範囲内にする。\n"
    "- cuts は冗長・無音・言い直しなど削るべき箇所を挙げる。\n"
    "- telops は要点や数字を強調する短い文言にする。\n"
    "- short_plan は goal に応じて設定（不要なら null 可）。\n"
    "- すべて日本語。値は現実的で具体的にする。"
)


def build_user_prompt(req: SuggestRequest) -> str:
    goal_map = {
        "improve": "通常動画としての完成度を上げる編集案。",
        "short": "ショート動画化を主目的にした編集案（short_plan 必須）。",
        "auto": "動画に最適な編集案（必要ならショート化も提案）。",
    }
    lines = [
        f"動画の長さ: 約 {req.duration_sec:.0f} 秒",
        f"目的: {goal_map[req.goal]}",
    ]
    if req.script.strip():
        lines.append("台本/文字起こし:\n" + req.script.strip())
    if req.style.strip():
        lines.append(
            "次の編集スタイルに寄せてください（テロップ・カット・BGM・テンポ・"
            "掴みの傾向を反映）:\n" + req.style.strip()
        )
    if req.notes.strip():
        lines.append(f"追加の要望: {req.notes.strip()}")
    lines.append("上記を踏まえ、編集案を JSON で出力してください。")
    return "\n".join(lines)


# ---- 編集スタイル学習 ----

_STYLE_SHAPE = """{
  "creator": "参考にした人/チャンネル名（分かれば）",
  "summary": "スタイルの一言要約",
  "pacing": "テンポ・カットの速さの特徴",
  "cut_style": "カットの特徴（ジャンプカット多用 等）",
  "telop_style": "テロップの使い方（大きい/効果音連動 等）",
  "sound_style": "BGM・効果音の傾向",
  "transitions": "トランジションの特徴",
  "hook_style": "冒頭の掴み方",
  "keywords": ["特徴キーワード1", "特徴キーワード2"]
}"""

STYLE_SYSTEM_PROMPT = (
    "あなたは動画編集のスタイル分析家です。"
    "指定されたクリエイター/参考動画/特徴の記述から、その編集スタイルを言語化します。"
    "（実際の動画は見られないため、名称・タイトル・記述から一般的に推測して構いません）\n\n"
    "出力は必ず次の JSON 形式のみ。説明文やコードフェンス(```)は付けない:\n"
    f"{_STYLE_SHAPE}\n\n"
    "ルール:\n"
    "- 実在すると断定できない場合も、与えられた手がかりから妥当なスタイル像を作る。\n"
    "- 各項目は編集に活かせるよう具体的に書く。\n"
    "- すべて日本語。"
)


def build_style_prompt(creator: str, source: str, notes: str) -> str:
    lines: list[str] = []
    if creator:
        lines.append(f"参考にしたい人/チャンネル: {creator}")
    if source:
        lines.append(f"参考動画の情報: {source}")
    if notes.strip():
        lines.append(f"好きな編集の特徴（本人の記述）: {notes.strip()}")
    if not lines:
        lines.append("一般的に人気のテンポ感のある編集スタイル")
    lines.append("このスタイルを JSON で言語化してください。")
    return "\n".join(lines)


AUTO_EDIT_SYSTEM_PROMPT = """あなたは動画編集ディレクターです。指示に従って編集プランを作ります。
出力は必ず次の JSON のみ（前後に説明文を付けない）:
{
  "summary": "編集方針の一言",
  "remove_silence": true,
  "cuts": [ {"start_sec": 0, "end_sec": 0, "reason": "冗長/言い直し等"} ],
  "telops": [ {"time_sec": 0, "text": "テロップ文言"} ],
  "materials": [ {"kind": "bgm|se|image|video", "query": "探すキーワード", "reason": "用途"} ]
}

ルール:
- 指示（例:「無音カット」「要点にテロップ」「BGMを付けたい」）を最優先で反映する。
- 基本は「テンポ重視」。無音・間延び・言い直しを削り、リズム良く見られるようにする。
  remove_silence は無音を自動カットするかどうか。指示が無ければ true。
- cuts は明らかに不要な区間だけを控えめに（動画の長さの範囲内、start<end）。自信が無ければ空でよい。
- telops は要点に簡潔な文言を（時刻は動画の長さの範囲内）。多すぎない（目安 30秒あたり2〜4個、全体で最大10個程度）。
  ★重要: テロップは表示時間を確保するため、時刻は最低でも2秒以上あけて散らす（連続で詰め込まない）。
  一瞬しか映らない大量のテロップは作らない。
- materials は「無料素材があると良い」ものを、用途を明確にして具体的に提案（BGM/効果音/画像/動画）。
  query は探しやすい日本語の検索語にする。実在URLは書かない（URLはシステム側で無料サイトを案内する）。
- 破壊的な指示や不明点は無理に編集せず、控えめにする。
"""


def build_auto_edit_prompt(
    instructions: str,
    duration_sec: float,
    silence_count: int,
    edit_heavy: bool = False,
) -> str:
    instr = instructions.strip()
    lines = []
    if instr:
        # ユーザーの細かい要望を最優先・冒頭に置き、一つずつ確実に反映させる
        lines.append("【ユーザーの編集指示（最優先・一つ残らず反映すること）】")
        lines.append(instr)
        lines.append(
            "↑の指示にある具体的な要望（例: 残す/削る箇所、テロップの文言や入れどころ、"
            "BGM/効果音の雰囲気、テンポ、強調したい点 等）を、可能な範囲で JSON の "
            "cuts / telops / materials / remove_silence にすべて落とし込むこと。"
            "指示に反する編集はしない。"
        )
        lines.append("")
    else:
        lines.append("編集の指示: （おまかせ。テンポよく見やすく）")
    lines.append(f"動画の長さ: 約 {duration_sec:.0f} 秒")
    lines.append(f"検出された無音区間: {silence_count} 箇所")
    lines.append("")
    if edit_heavy:
        # 「しゃべるだけの動画」にしないための編集多めモード
        # 尺に応じてテロップ数の目安を出す（一瞬表示にならないよう間隔は確保）
        target_telops = max(6, min(24, int(duration_sec / 6)))
        lines.append("【編集多めモード（しゃべるだけの動画にしない）】")
        lines.append(
            "画がしゃべっているだけにならないよう、テロップと画面の変化を積極的に入れる。"
        )
        lines.append(
            f"- telops を多め（目安 {target_telops} 個前後、話の要点・数字・キーワードごと）"
            "に入れる。ただし各テロップは最低1.8秒あけ、一瞬しか映らない詰め込みはしない。"
        )
        lines.append(
            "- 場所・話題の切り替わりには『見出しテロップ』や指し示す記号を活用する。"
            "例: 『① まず〜』『▶ ポイント』『★ ここ重要』『→ こうなる』『📍 手順1』"
            "『💡 コツ』など、記号（→ ★ ▶ ① ② ③ 📍 💡 ✅ 🔍）を織り交ぜて視覚的に飽きさせない。"
        )
        lines.append(
            "- materials には話題に合う image（挿絵・図・アイコン）を複数、query を具体的にして"
            "提案する（BGM/効果音だけでなく画像・動画のb-rollも）。ダウンロードして差し込めるようにする。"
        )
        lines.append("")
    lines.append("この動画の編集プランを JSON で作ってください。")
    return "\n".join(lines)
