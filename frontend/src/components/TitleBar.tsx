// フレームレスウィンドウ用のカスタムタイトルバー。
// 中央のドラッグ領域でウィンドウ移動、右側で最小化/最大化/閉じる。
import Logo from './Logo'

const ctl = () => window.videocraft?.window

export default function TitleBar() {
  return (
    <div className="titlebar">
      <div className="titlebar-drag">
        <span className="titlebar-logo">
          <Logo size={18} />
        </span>
        <span className="titlebar-title">AI VideoCraft</span>
        <span className="titlebar-tag">Studio</span>
      </div>
      <div className="titlebar-controls">
        <button
          className="tb-btn"
          aria-label="最小化"
          onClick={() => ctl()?.minimize()}
        >
          <svg width="11" height="11" viewBox="0 0 11 11">
            <rect x="1" y="5" width="9" height="1" fill="currentColor" />
          </svg>
        </button>
        <button
          className="tb-btn"
          aria-label="最大化"
          onClick={() => ctl()?.toggleMaximize()}
        >
          <svg width="11" height="11" viewBox="0 0 11 11">
            <rect
              x="1.5"
              y="1.5"
              width="8"
              height="8"
              fill="none"
              stroke="currentColor"
            />
          </svg>
        </button>
        <button
          className="tb-btn tb-close"
          aria-label="閉じる"
          onClick={() => ctl()?.close()}
        >
          <svg width="11" height="11" viewBox="0 0 11 11">
            <path
              d="M1 1 L10 10 M10 1 L1 10"
              stroke="currentColor"
              strokeWidth="1.1"
            />
          </svg>
        </button>
      </div>
    </div>
  )
}
