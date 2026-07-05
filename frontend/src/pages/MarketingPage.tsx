import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Article, MarketingResponse, ProviderInfo } from '../types'
import CopyButton from '../components/CopyButton'

export default function MarketingPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')

  const [topic, setTopic] = useState('')
  const [keywordsText, setKeywordsText] = useState('')
  const [count, setCount] = useState(3)
  const [tone, setTone] = useState('')

  const [result, setResult] = useState<MarketingResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listProviders().then((ps) => {
      setProviders(ps)
      const first = ps.find((p) => p.configured) ?? ps[0]
      if (first) setProvider(first.id)
    })
  }, [])

  useEffect(() => {
    if (!provider) return
    setModel('')
    api
      .listModels(provider)
      .then((ms) => {
        setModels(ms)
        setModel(ms[0] ?? '')
      })
      .catch(() => setModels([]))
  }, [provider])

  const keywords = keywordsText
    .split('\n')
    .map((k) => k.trim())
    .filter(Boolean)

  async function generate() {
    if (!topic.trim() || busy) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.generateMarketing({
        topic: topic.trim(),
        keywords: keywords.length ? keywords : undefined,
        count,
        tone: tone.trim() || undefined,
        provider,
        model: model || undefined,
      })
      setResult(res)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="dev-banner">
        <span className="dev-badge">DEV</span>
        開発者専用ツール。記事・SEOコンテンツを量産して製品を宣伝します（エンドユーザーには非公開）。
      </div>

      <h1>
        <span className="gradient-text">宣伝AI</span>
      </h1>
      <p className="subtitle">
        キーワードごとにSEO記事を量産します。未指定ならAIがキーワードを提案します。
      </p>

      <section className="card">
        <input
          className="input"
          placeholder="宣伝対象（例: AI VideoCraft / AI動画編集アプリ）"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <div className="field-label">狙うキーワード（1行に1つ・任意）</div>
        <textarea
          className="input"
          rows={3}
          placeholder={'AI 動画編集 無料\n動画 自動テロップ やり方\nショート動画 作り方'}
          value={keywordsText}
          onChange={(e) => setKeywordsText(e.target.value)}
        />
        <div className="plan-form-grid">
          <label>
            記事数（キーワード未指定時）
            <input
              className="input"
              type="number"
              min={1}
              max={10}
              value={count}
              onChange={(e) =>
                setCount(Math.min(10, Math.max(1, Number(e.target.value) || 1)))
              }
              disabled={keywords.length > 0}
            />
          </label>
          <label>
            トーン・ターゲット
            <input
              className="input"
              placeholder="例: 初心者向け・カジュアル"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
            />
          </label>
          <label>
            プロバイダー
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name} {p.configured ? '' : '（未設定）'}
                </option>
              ))}
            </select>
          </label>
          <label>
            モデル
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {models.length === 0 && <option value="">（モデルなし）</option>}
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="gen-note muted">
          {keywords.length > 0
            ? `${keywords.length} 個のキーワードで ${keywords.length} 記事を生成`
            : `AIがキーワードを提案し ${count} 記事を生成`}
        </div>
        {error && <div className="banner error">{error}</div>}
        <button className="btn primary" onClick={generate} disabled={busy}>
          {busy ? '量産中…（記事ごとに生成）' : '記事を量産'}
        </button>
      </section>

      {result && (
        <section>
          <div className="plan-badges">
            <span className="badge ok">
              {result.generated} / {result.requested} 記事生成
            </span>
            <span className="muted">
              {result.provider} / {result.model}
            </span>
          </div>
          {result.articles.map((a, i) => (
            <ArticleCard key={i} article={a} />
          ))}
        </section>
      )}
    </div>
  )
}

function ArticleCard({ article }: { article: Article }) {
  return (
    <div className="card article-card">
      <div className="article-head">
        <h2>{article.title}</h2>
        <CopyButton text={article.body_markdown} label="本文コピー" />
      </div>

      <div className="article-meta">
        {article.target_keyword && (
          <span className="kw-badge">🎯 {article.target_keyword}</span>
        )}
        {article.slug && <span className="mono slug">/{article.slug}</span>}
      </div>

      {article.meta_description && (
        <div className="meta-desc">
          <div className="field-label">
            メタディスクリプション
            <CopyButton text={article.meta_description} />
          </div>
          <p className="muted">{article.meta_description}</p>
        </div>
      )}

      {article.keywords.length > 0 && (
        <div className="chip-row article-kws">
          {article.keywords.map((k, i) => (
            <span key={i} className="chip">
              {k}
            </span>
          ))}
        </div>
      )}

      <details className="article-body-wrap">
        <summary>本文を表示（Markdown）</summary>
        <pre className="article-body">{article.body_markdown}</pre>
      </details>
    </div>
  )
}
