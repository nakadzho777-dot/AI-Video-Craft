"""AI自動撮影の台本生成プロンプト."""
from __future__ import annotations

SYSTEM_PROMPT = """あなたは、指定されたWebサイトの紹介・チュートリアル動画を自動制作するための
「ブラウザ操作台本」を作るアシスタントです。

出力は必ず次の JSON のみ（前後に説明文を付けない）:
{
  "title": "動画のタイトル",
  "url": "最初に開くURL（入力されたものを使う）",
  "steps": [
    {
      "title": "短いラベル",
      "action": "goto | click | fill | press | scroll | wait",
      "target": "click/fill の対象。実際に画面に見えるボタン名・リンク文言・入力欄のラベルやプレースホルダを、そのままの文字で",
      "value": "fill の入力文字 / press のキー(例 Enter) / goto のURL / scroll の量(例 600)",
      "narration": "このステップの間に読み上げるナレーション（日本語・話し言葉・1〜2文）"
    }
  ]
}

ルール:
- ステップ数は 4〜8 個。長すぎない、分かりやすい流れにする。
- ★画面に「動き」を持たせる：静止画のような退屈な間を作らない。
  ・スクロール(action=scroll, value=400〜800)でページを少しずつ見せながら解説する。
  ・要素をクリックして画面が変化する様子（展開・遷移・メニュー表示）を見せる。
  ・単なる wait を続けない。待つ場合も直前後にスクロールや遷移を挟む。
  ・目安として scroll を全体の1/3程度は入れ、視線を上から下へ誘導する。
- narration は「今まさに画面で起きている動き・変化」に合わせる（スクロールで現れた内容、クリックで開いた画面などに言及）。
- click の target は「ログイン」「詳細を見る」など、実際にページ上に表示されている可能性が高い短い文言にする（CSSセレクタや推測の英語IDは避ける）。
- 最初のステップは通常、ページ全体を上から見せる（action は scroll）と自然。
- 操作が失敗しても動画は続くので、確実そうな操作を選ぶ。危険な操作（購入・削除・送信）は避ける。
- narration は視聴者に語りかける自然な日本語。誇張せず、その画面で何が見えるか・何をするかを説明する。
- 不明な点は無理に操作せず scroll + narration で画面を見せながら補う。
"""


def _instructions_block(instructions: str) -> str:
    return (
        "\n【ユーザー指定の手順】以下の手順に厳密に従ってください。"
        "順番を守り、勝手に手順を足したり省いたりしないこと。"
        "各手順を1ステップにし、その操作(action/target/value)に落とし込み、"
        "手順に合ったnarrationを付けてください:\n" + instructions.strip()
    )


_STYLE_TONE = {
    "kaisetsu": "\nナレーションは「ゆっくり解説」風の、視聴者に語りかける丁寧で分かりやすい口調にする。",
    "jikkyou": "\nナレーションは「ゆっくり実況」風の、テンポよく画面に反応する軽快な口調にする。",
}


def build_user_prompt(
    url: str,
    topic: str,
    notes: str,
    instructions: str = "",
    style: str = "normal",
    urls: list[str] | None = None,
) -> str:
    lines = [
        f"対象URL: {url}",
        f"動画のテーマ: {topic or '（サイトの紹介動画）'}",
    ]
    urls = [u for u in (urls or []) if u.strip()]
    if len(urls) > 1:
        lines.append(
            "利用可能なページ（この中だけを goto で行き来できる。他は開かない）:\n"
            + "\n".join(f"- {u}" for u in urls)
        )
    if style in _STYLE_TONE:
        lines.append(_STYLE_TONE[style].strip())
    if notes.strip():
        lines.append(f"追加の要望: {notes.strip()}")
    if instructions.strip():
        lines.append(_instructions_block(instructions))
        lines.append("")
        lines.append(
            "上記の手順に沿って、ブラウザ操作台本を JSON で作ってください。"
        )
    else:
        lines.append("")
        lines.append(
            "このサイトを紹介する動画のブラウザ操作台本を JSON で作ってください。"
        )
    return "\n".join(lines)


DESKTOP_SYSTEM_PROMPT = """あなたは、Windowsのデスクトップアプリの紹介・操作解説動画のための
「ナレーション台本（＋できる範囲の自動操作）」を作るアシスタントです。

出力は必ず次の JSON のみ:
{
  "title": "動画のタイトル",
  "window_title": "対象ウィンドウのタイトル（入力されたものを使う）",
  "steps": [
    {
      "title": "短いラベル",
      "action": "click | type | key | scroll | wait",
      "target": "click の対象。画面に見えるボタン名・メニュー名など、そのままの文字",
      "value": "type の入力文字 / key のキー(例 {ENTER}) / scroll の量(例 3)",
      "narration": "このステップの間に読み上げるナレーション（日本語・話し言葉・1〜2文）"
    }
  ]
}

重要な前提:
- デスクトップアプリはWeb と違い、操作対象を確実に指定できないことが多い。
  そのため **narration（解説）を主役** にし、action は確実そうなものだけ控えめに入れる。
- ★それでも画面に「動き」を作る：スクロール(action=scroll)やタブ/メニュー移動で画面が
  変化する様子を見せ、静止しっぱなしにしない。narration は今画面で動いている内容に合わせる。
- click の target は「ファイル」「保存」など、実際にメニューやボタンに表示される短い文言。
- 破壊的・不可逆な操作（削除・上書き保存・送信・購入・設定変更の確定）は絶対に入れない。
- 自信が無いステップは action を "wait" か "scroll" にして narration で画面を見せながら解説する。
- ステップ数は 4〜7 個。視聴者に画面の見方・使い方が伝わる流れにする。
"""


def build_desktop_prompt(
    window_title: str, topic: str, notes: str, instructions: str = ""
) -> str:
    lines = [
        f"対象ウィンドウ: {window_title}",
        f"動画のテーマ: {topic or '（アプリの使い方紹介）'}",
    ]
    if notes.strip():
        lines.append(f"追加の要望: {notes.strip()}")
    if instructions.strip():
        lines.append(_instructions_block(instructions))
        lines.append("")
        lines.append(
            "上記の手順に沿って、ナレーション台本（＋確実な範囲の操作）を "
            "JSON で作ってください。破壊的・不可逆な操作は含めないこと。"
        )
    else:
        lines.append("")
        lines.append(
            "このアプリを紹介・解説する動画のナレーション台本（＋確実な範囲の操作）を "
            "JSON で作ってください。"
        )
    return "\n".join(lines)
