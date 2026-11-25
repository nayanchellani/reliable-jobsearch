import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

interface Job {
  id: number
  title: string
  company: string
  location: string
  remote: boolean
  job_type: string
  experience_level: string
  salary?: string
  source: string
  apply_url: string
  posted_at?: string
  first_seen_at?: string
  status: string
  raw?: any
  description?: string
}

interface ResumeProfile {
  name: string
  email?: string
  phone?: string
  years_experience: number
  key_skills: string[]
  previous_companies: string[]
  achievements: string[]
  education: string[]
}

const API_BASE = 'http://localhost:8000'
const api = axios.create({ baseURL: API_BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Company initials avatar ──────────────────────────────────────────────────
function CompanyAvatar({ company }: { company: string }) {
  const name = company.toLowerCase()
  let bg = 'bg-neutral-200'
  let text = 'text-neutral-600'

  if (name.includes('meta') || name.includes('facebook')) { bg = 'bg-blue-600'; text = 'text-white' }
  else if (name.includes('google')) { bg = 'bg-neutral-900'; text = 'text-white' }
  else if (name.includes('microsoft')) { bg = 'bg-blue-700'; text = 'text-white' }
  else if (name.includes('amazon')) { bg = 'bg-amber-500'; text = 'text-white' }
  else if (name.includes('spotify')) { bg = 'bg-green-500'; text = 'text-white' }
  else if (name.includes('apple')) { bg = 'bg-neutral-800'; text = 'text-white' }

  const initials = company.trim().slice(0, 2).toUpperCase() || 'JB'
  return (
    <div className={`w-10 h-10 rounded-lg ${bg} ${text} flex items-center justify-center font-semibold text-sm shrink-0`}>
      {initials}
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────
const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
  </svg>
)
const FileIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
  </svg>
)
const SettingsIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
  </svg>
)
const LogoutIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
  </svg>
)
const BookmarkIcon = ({ filled }: { filled: boolean }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
  </svg>
)
const UploadIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
  </svg>
)
const RefreshIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
  </svg>
)
const ExternalIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
  </svg>
)

// ── Helpers ───────────────────────────────────────────────────────────────────
function postedAgo(dateStr?: string): string {
  if (!dateStr) return 'Recently'
  const ms = Date.now() - new Date(dateStr).getTime()
  const h = Math.floor(ms / 3600000)
  if (h < 1) return 'Just now'
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d}d ago`
  return `${Math.floor(d / 7)}w ago`
}

function formatJobType(t?: string): string {
  if (!t) return 'Full time'
  return t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatExpLevel(l?: string): string {
  if (!l) return 'Mid'
  return l.charAt(0).toUpperCase() + l.slice(1)
}

// ── Auth screen ───────────────────────────────────────────────────────────────
function AuthScreen({ onAuth }: { onAuth: () => void }) {
  const [isLogin, setIsLogin] = useState(true)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!isLogin && password !== confirm) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      const path = isLogin ? '/auth/login' : '/auth/register'
      const res = await axios.post(`${API_BASE}${path}`, { email, password, confirm_password: confirm })
      localStorage.setItem('token', res.data.token)
      onAuth()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-neutral-50 flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <span className="text-lg font-semibold text-neutral-900 tracking-tight">Job Aggregator</span>
          <p className="text-sm text-neutral-500 mt-1">{isLogin ? 'Sign in to continue' : 'Create an account'}</p>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-neutral-500 mb-1">Email</label>
            <input
              type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-neutral-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-neutral-500 mb-1">Password</label>
            <input
              type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-neutral-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
            />
          </div>
          {!isLogin && (
            <div>
              <label className="block text-xs font-medium text-neutral-500 mb-1">Confirm password</label>
              <input
                type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-neutral-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
              />
            </div>
          )}
          {error && <p className="text-xs text-red-600">{error}</p>}
          <button
            type="submit" disabled={loading}
            className="w-full py-2 bg-orange-600 hover:bg-orange-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 mt-2"
          >
            {loading ? 'Please wait…' : isLogin ? 'Sign in' : 'Create account'}
          </button>
        </form>
        <button
          onClick={() => { setIsLogin(!isLogin); setError('') }}
          className="mt-4 text-xs text-neutral-500 hover:text-neutral-700 transition-colors"
        >
          {isLogin ? "Don't have an account? Register" : 'Already have an account? Sign in'}
        </button>
      </div>
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [authenticated, setAuthenticated] = useState(!!localStorage.getItem('token'))
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('posted_at_desc')
  const [activeTab, setActiveTab] = useState<'search' | 'resume' | 'settings'>('search')
  const [savedIds, setSavedIds] = useState<number[]>([])
  const [page, setPage] = useState(1)
  const [perPage] = useState(20)

  // Resume
  const [resumeProfile, setResumeProfile] = useState<ResumeProfile | null>(null)
  const [uploadingResume, setUploadingResume] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Cover letter modal
  const [coverJob, setCoverJob] = useState<Job | null>(null)
  const [coverText, setCoverText] = useState('')
  const [generatingCover, setGeneratingCover] = useState(false)
  const [coverTone, setCoverTone] = useState('professional')
  const [matchInfo, setMatchInfo] = useState<{ score: number; strengths: string[]; gaps: string[] } | null>(null)

  // Settings
  const [settings, setSettings] = useState({
    llm_base_url: '', llm_api_key: '', llm_model: 'auto',
    greenhouse_token: '', lever_company: '', ashby_name: '',
  })

  // ── Data fetching ──────────────────────────────────────────────────────────
  const fetchJobs = async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, per_page: perPage, sort }
      if (query.trim()) params.q = query.trim()
      const res = await api.get('/jobs', { params })
      setJobs(res.data || [])
    } catch {
      setJobs([])
    } finally {
      setLoading(false)
    }
  }

  const fetchResumeProfile = async () => {
    try {
      const res = await api.get('/resume/profile')
      if (res.data) setResumeProfile(res.data)
    } catch { /* no profile yet */ }
  }

  const triggerSync = async () => {
    setSyncing(true)
    try {
      await api.post('/connectors/sync')
      await fetchJobs()
    } catch (e: any) {
      console.warn('Sync failed:', e.message)
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => { if (authenticated) { fetchJobs(); fetchResumeProfile() } }, [sort, page, authenticated])

  // ── Actions ────────────────────────────────────────────────────────────────
  const logout = () => { localStorage.removeItem('token'); setAuthenticated(false) }

  const toggleSave = (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    setSavedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }

  const openJob = (url: string) => url && window.open(url, '_blank', 'noopener,noreferrer')

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingResume(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.post('/resume/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setResumeProfile(res.data)
    } catch { alert('Failed to parse resume') } finally { setUploadingResume(false) }
  }

  const saveProfile = async () => {
    if (!resumeProfile) return
    try {
      const res = await api.put('/resume/profile', resumeProfile)
      setResumeProfile(res.data)
    } catch { alert('Failed to save profile') }
  }

  const generateCoverLetter = async (job: Job, e: React.MouseEvent) => {
    e.stopPropagation()
    setCoverJob(job)
    setCoverText('')
    setMatchInfo(null)
    setGeneratingCover(true)
    try {
      const res = await api.post('/generate-cover-letter', { job_id: job.id, tone: coverTone })
      setCoverText(res.data.cover_letter)
      setMatchInfo({ score: res.data.match_score, strengths: res.data.strengths, gaps: res.data.gaps })
    } catch {
      setCoverText(`Dear Hiring Team at ${job.company},\n\nI am writing to express my interest in the ${job.title} role. My background aligns with your requirements and I would welcome the opportunity to discuss further.\n\nSincerely,\n${resumeProfile?.name || 'Applicant'}`)
      setMatchInfo({ score: 75, strengths: ['Relevant experience'], gaps: [] })
    } finally { setGeneratingCover(false) }
  }

  const exportCover = () => {
    if (!coverText) return
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([coverText], { type: 'text/plain' }))
    a.download = `${coverJob?.company || 'Job'}_cover_letter.txt`
    a.click()
  }

  const saveSettings = async () => {
    try { await api.put('/settings', settings) }
    catch { alert('Failed to save settings') }
  }

  // ── Auth gate ──────────────────────────────────────────────────────────────
  if (!authenticated) return <AuthScreen onAuth={() => setAuthenticated(true)} />

  // ── Nav item helper ────────────────────────────────────────────────────────
  const NavItem = ({ tab, icon, label }: { tab: 'search' | 'resume' | 'settings'; icon: React.ReactNode; label: string }) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
        activeTab === tab
          ? 'bg-orange-50 text-orange-700 font-medium'
          : 'text-neutral-500 hover:text-neutral-800 hover:bg-neutral-100'
      }`}
    >
      <span className="shrink-0">{icon}</span>
      <span>{label}</span>
    </button>
  )

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900 flex flex-col antialiased">

      {/* Header */}
      <header className="h-12 px-6 flex items-center justify-between border-b border-neutral-200 bg-white shrink-0">
        <span className="text-sm font-semibold tracking-tight text-neutral-900">Job Aggregator</span>

        {/* Search */}
        <div className="flex-1 max-w-xl mx-8">
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400">
              <SearchIcon />
            </span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && fetchJobs()}
              placeholder="Search jobs by title or company"
              className="w-full pl-9 pr-4 py-1.5 text-sm border border-neutral-200 rounded-md bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 focus:bg-white transition-colors placeholder:text-neutral-400"
            />
          </div>
        </div>

        {/* Right */}
        <div className="flex items-center gap-3">
          {resumeProfile && (
            <span className="text-xs text-emerald-700 font-medium bg-emerald-50 border border-emerald-200 px-2 py-1 rounded-md">
              Resume loaded
            </span>
          )}
          <button onClick={logout} className="text-xs text-neutral-500 hover:text-neutral-800 transition-colors flex items-center gap-1.5">
            <LogoutIcon />
            Sign out
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">

        {/* Sidebar */}
        <aside className="w-52 bg-white border-r border-neutral-200 flex flex-col py-4 px-3 shrink-0">
          <nav className="flex flex-col gap-1">
            <NavItem tab="search" icon={<SearchIcon />} label="Search" />
            <NavItem tab="resume" icon={<FileIcon />} label="My resume" />
            <NavItem tab="settings" icon={<SettingsIcon />} label="Settings" />
          </nav>
          <div className="mt-auto pt-4 border-t border-neutral-100">
            <button
              onClick={logout}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-neutral-500 hover:text-red-600 hover:bg-red-50 transition-colors"
            >
              <LogoutIcon />
              <span>Sign out</span>
            </button>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 overflow-y-auto p-6">

          {/* ── SEARCH TAB ── */}
          {activeTab === 'search' && (
            <div className="max-w-5xl space-y-5">

              {/* Top bar: count + controls */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-neutral-900 tabular-nums">
                    {jobs.length} jobs
                  </span>
                  <button
                    onClick={triggerSync}
                    disabled={syncing}
                    className="flex items-center gap-1.5 text-xs text-neutral-500 hover:text-orange-600 transition-colors disabled:opacity-50"
                  >
                    <RefreshIcon />
                    {syncing ? 'Syncing…' : 'Sync now'}
                  </button>
                </div>
                <div className="flex items-center gap-2 text-xs text-neutral-500">
                  <span>Sort</span>
                  <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                    className="border border-neutral-200 rounded-md px-2 py-1 text-xs bg-white focus:outline-none"
                  >
                    <option value="posted_at_desc">Newest first</option>
                    <option value="posted_at_asc">Oldest first</option>
                    <option value="title_asc">Title A–Z</option>
                  </select>
                </div>
              </div>

              {/* Job list */}
              {loading ? (
                <div className="py-16 text-center text-sm text-neutral-400">Loading…</div>
              ) : jobs.length === 0 ? (
                <div className="py-16 text-center space-y-3">
                  <p className="text-sm text-neutral-500">No jobs found.</p>
                  <button
                    onClick={triggerSync}
                    disabled={syncing}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-orange-600 hover:bg-orange-700 text-white rounded-md transition-colors disabled:opacity-50"
                  >
                    <RefreshIcon />
                    {syncing ? 'Syncing…' : 'Fetch jobs now'}
                  </button>
                  <p className="text-xs text-neutral-400">Pulls from Remotive, Arbeitnow, RemoteOK and more</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {jobs.map((job) => (
                    <div
                      key={job.id}
                      onClick={() => openJob(job.apply_url)}
                      className="bg-white border border-neutral-200 rounded-xl p-5 flex flex-col gap-4 cursor-pointer hover:border-orange-300 hover:shadow-sm transition-all group"
                    >
                      {/* Top: avatar + title + bookmark */}
                      <div className="flex items-start gap-3">
                        <CompanyAvatar company={job.company} />
                        <div className="flex-1 min-w-0">
                          <h2 className="text-sm font-medium text-neutral-900 group-hover:text-orange-700 transition-colors leading-tight truncate">
                            {job.title}
                          </h2>
                          <p className="text-xs text-neutral-500 mt-0.5 truncate">
                            {job.company} · {job.location || 'Remote'}
                          </p>
                        </div>
                        <button
                          onClick={(e) => toggleSave(job.id, e)}
                          className={`shrink-0 p-1 rounded transition-colors ${savedIds.includes(job.id) ? 'text-orange-600' : 'text-neutral-300 hover:text-neutral-500'}`}
                        >
                          <BookmarkIcon filled={savedIds.includes(job.id)} />
                        </button>
                      </div>

                      {/* Tags */}
                      <div className="flex flex-wrap gap-1.5">
                        <span className="px-2 py-0.5 rounded-md border border-neutral-200 text-xs text-neutral-500 bg-neutral-50 capitalize">
                          {formatJobType(job.job_type)}
                        </span>
                        {job.remote && (
                          <span className="px-2 py-0.5 rounded-md border border-neutral-200 text-xs text-neutral-500 bg-neutral-50">
                            Remote
                          </span>
                        )}
                        <span className="px-2 py-0.5 rounded-md border border-neutral-200 text-xs text-neutral-500 bg-neutral-50 capitalize">
                          {formatExpLevel(job.experience_level)}
                        </span>
                        <span className="px-2 py-0.5 rounded-md border border-orange-100 text-xs text-orange-600 bg-orange-50 capitalize">
                          {job.source}
                        </span>
                      </div>

                      {/* Bottom: time + salary + cover letter */}
                      <div className="flex items-center justify-between pt-3 border-t border-neutral-100">
                        <span className="text-xs text-neutral-400 tabular-nums">
                          {postedAgo(job.posted_at || job.first_seen_at)}
                        </span>
                        <div className="flex items-center gap-2">
                          {job.salary && (
                            <span className="text-xs font-medium text-neutral-700 tabular-nums">{job.salary}</span>
                          )}
                          <button
                            onClick={(e) => generateCoverLetter(job, e)}
                            className="text-xs px-2.5 py-1 border border-neutral-200 hover:border-orange-300 hover:text-orange-700 rounded-md text-neutral-600 transition-colors"
                          >
                            Cover letter
                          </button>
                          <span className="flex items-center gap-1 text-xs text-neutral-400">
                            <ExternalIcon />
                            Apply
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Pagination */}
              {jobs.length > 0 && (
                <div className="flex items-center justify-between pt-4 border-t border-neutral-200 text-xs text-neutral-500">
                  <span className="tabular-nums">{jobs.length} results</span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setPage(Math.max(1, page - 1))}
                      disabled={page === 1}
                      className="px-2.5 py-1 border border-neutral-200 rounded-md hover:bg-neutral-50 disabled:opacity-40 transition-colors"
                    >
                      ‹
                    </button>
                    <span className="px-3 py-1 bg-orange-600 text-white rounded-md tabular-nums">{page}</span>
                    <button
                      onClick={() => setPage(page + 1)}
                      className="px-2.5 py-1 border border-neutral-200 rounded-md hover:bg-neutral-50 transition-colors"
                    >
                      ›
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── RESUME TAB ── */}
          {activeTab === 'resume' && (
            <div className="max-w-2xl space-y-6">
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-base font-semibold text-neutral-900">Resume</h1>
                  <p className="text-xs text-neutral-500 mt-1">Upload a PDF or DOCX to enable match scoring and cover letter generation</p>
                </div>
                <div>
                  <input type="file" ref={fileInputRef} onChange={handleFileUpload} accept=".pdf,.docx,.txt" className="hidden" />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingResume}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium bg-orange-600 hover:bg-orange-700 text-white rounded-md transition-colors disabled:opacity-50"
                  >
                    <UploadIcon />
                    {uploadingResume ? 'Parsing…' : 'Upload resume'}
                  </button>
                </div>
              </div>

              {resumeProfile ? (
                <div className="bg-white border border-neutral-200 rounded-xl p-5 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    {[
                      { label: 'Full name', key: 'name', value: resumeProfile.name },
                      { label: 'Email', key: 'email', value: resumeProfile.email || '' },
                      { label: 'Phone', key: 'phone', value: resumeProfile.phone || '' },
                      { label: 'Years of experience', key: 'years_experience', value: String(resumeProfile.years_experience) },
                    ].map(({ label, key, value }) => (
                      <div key={key}>
                        <label className="block text-xs font-medium text-neutral-500 mb-1">{label}</label>
                        <input
                          value={value}
                          onChange={(e) => setResumeProfile({ ...resumeProfile, [key]: key === 'years_experience' ? parseFloat(e.target.value) || 0 : e.target.value })}
                          className="w-full px-3 py-2 text-sm border border-neutral-200 rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                        />
                      </div>
                    ))}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-neutral-500 mb-1">Key skills (comma-separated)</label>
                    <input
                      value={resumeProfile.key_skills.join(', ')}
                      onChange={(e) => setResumeProfile({ ...resumeProfile, key_skills: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                      className="w-full px-3 py-2 text-sm border border-neutral-200 rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-neutral-500 mb-1">Previous employers (comma-separated)</label>
                    <input
                      value={resumeProfile.previous_companies.join(', ')}
                      onChange={(e) => setResumeProfile({ ...resumeProfile, previous_companies: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                      className="w-full px-3 py-2 text-sm border border-neutral-200 rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                    />
                  </div>
                  <button
                    onClick={saveProfile}
                    className="w-full py-2 bg-orange-600 hover:bg-orange-700 text-white text-sm font-medium rounded-md transition-colors"
                  >
                    Save profile
                  </button>
                </div>
              ) : (
                <div className="bg-white border-2 border-dashed border-neutral-200 rounded-xl p-12 text-center space-y-3">
                  <div className="flex justify-center text-neutral-300">
                    <FileIcon />
                  </div>
                  <p className="text-sm font-medium text-neutral-700">No resume uploaded</p>
                  <p className="text-xs text-neutral-400">Upload a PDF or DOCX to enable skill extraction, job match scores, and tailored cover letters</p>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border border-neutral-200 hover:border-orange-300 hover:text-orange-700 rounded-md transition-colors"
                  >
                    <UploadIcon />
                    Choose file
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ── SETTINGS TAB ── */}
          {activeTab === 'settings' && (
            <div className="max-w-lg space-y-6">
              <div>
                <h1 className="text-base font-semibold text-neutral-900">Settings</h1>
                <p className="text-xs text-neutral-500 mt-1">Configure your LLM endpoint and ATS tokens</p>
              </div>

              <div className="bg-white border border-neutral-200 rounded-xl p-5 space-y-4">
                <div>
                  <p className="text-xs font-medium text-neutral-500 mb-3 uppercase tracking-wide">LLM</p>
                  {[
                    { label: 'Base URL', key: 'llm_base_url', placeholder: 'https://api.openai.com/v1' },
                    { label: 'API key', key: 'llm_api_key', placeholder: 'sk-…' },
                    { label: 'Model', key: 'llm_model', placeholder: 'gpt-4o-mini' },
                  ].map(({ label, key, placeholder }) => (
                    <div key={key} className="mb-3">
                      <label className="block text-xs font-medium text-neutral-500 mb-1">{label}</label>
                      <input
                        value={(settings as any)[key]}
                        onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
                        placeholder={placeholder}
                        className="w-full px-3 py-2 text-sm border border-neutral-200 rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                    </div>
                  ))}
                </div>

                <div className="pt-4 border-t border-neutral-100">
                  <p className="text-xs font-medium text-neutral-500 mb-3 uppercase tracking-wide">ATS tokens</p>
                  {[
                    { label: 'Greenhouse token', key: 'greenhouse_token', placeholder: 'e.g. stripe' },
                    { label: 'Lever company', key: 'lever_company', placeholder: 'e.g. netflix' },
                    { label: 'Ashby board name', key: 'ashby_name', placeholder: 'e.g. linear' },
                  ].map(({ label, key, placeholder }) => (
                    <div key={key} className="mb-3">
                      <label className="block text-xs font-medium text-neutral-500 mb-1">{label}</label>
                      <input
                        value={(settings as any)[key]}
                        onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
                        placeholder={placeholder}
                        className="w-full px-3 py-2 text-sm border border-neutral-200 rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                    </div>
                  ))}
                </div>

                <button
                  onClick={saveSettings}
                  className="w-full py-2 bg-orange-600 hover:bg-orange-700 text-white text-sm font-medium rounded-md transition-colors"
                >
                  Save settings
                </button>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Cover letter modal */}
      {coverJob && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setCoverJob(null)}>
          <div
            className="bg-white rounded-xl max-w-lg w-full p-6 space-y-4 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-sm font-semibold text-neutral-900">Cover letter</h2>
                <p className="text-xs text-neutral-500 mt-0.5">{coverJob.title} at {coverJob.company}</p>
              </div>
              <button onClick={() => setCoverJob(null)} className="text-neutral-400 hover:text-neutral-600 transition-colors text-lg leading-none">×</button>
            </div>

            {/* Match score */}
            {matchInfo && (
              <div className="flex items-center gap-3 p-3 bg-neutral-50 border border-neutral-200 rounded-lg text-xs">
                <span className="font-semibold text-neutral-900 tabular-nums text-sm">{matchInfo.score}/100</span>
                <span className="text-neutral-500">match score</span>
                {matchInfo.strengths[0] && (
                  <span className="text-neutral-400 truncate">· {matchInfo.strengths[0]}</span>
                )}
              </div>
            )}

            {/* Tone selector */}
            <div className="flex gap-2">
              {(['professional', 'enthusiastic', 'concise'] as const).map((tone) => (
                <button
                  key={tone}
                  onClick={() => setCoverTone(tone)}
                  className={`px-3 py-1 text-xs rounded-md capitalize transition-colors ${
                    coverTone === tone
                      ? 'bg-orange-600 text-white'
                      : 'border border-neutral-200 text-neutral-500 hover:border-orange-300'
                  }`}
                >
                  {tone}
                </button>
              ))}
            </div>

            {/* Text */}
            <textarea
              rows={9}
              value={generatingCover ? 'Generating…' : coverText}
              onChange={(e) => setCoverText(e.target.value)}
              className="w-full p-3 border border-neutral-200 rounded-lg text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 font-sans resize-none"
            />

            {/* Actions */}
            <div className="flex items-center justify-between pt-2">
              <a
                href={coverJob.apply_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-orange-600 hover:underline flex items-center gap-1"
              >
                View posting <ExternalIcon />
              </a>
              <div className="flex gap-2">
                <button
                  onClick={exportCover}
                  className="px-3 py-1.5 text-xs border border-neutral-200 hover:bg-neutral-50 rounded-md transition-colors"
                >
                  Export
                </button>
                <button
                  onClick={() => openJob(coverJob.apply_url)}
                  className="px-4 py-1.5 text-xs font-medium bg-orange-600 hover:bg-orange-700 text-white rounded-md transition-colors"
                >
                  Apply
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
